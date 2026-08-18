import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass

import websockets
from aiohttp import web

from api.websocket import WebSocketHandler, broadcast_state, configure_websocket, send_message
from faults.injector import FaultInjector, FaultType
from models.conveyor import ConveyorNode
from models.lift import LiftNode
from models.pallet import Pallet
from models.plc import CentralPLC
from models.rack import StorageRack
from models.scanner import SafetyScanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("sim")

# Node layout (world coordinates):
# Entry conveyor (CNV-A): x=0..4, z=1.0, runs in +x direction
# Mid conveyor (CNV-B): x=4..7, z=1.0, runs in +x direction
# Lift (LIFT-1): x=7, z=1.0, moves in y
# Exit conveyor (CNV-C): x=7..10, z=1.0, runs in +x direction
# Rack: x=6..10, z=2..5

TICK_HZ = 60
TICK_DT = 1.0 / TICK_HZ
FAULT_ERROR_MESSAGE = "Invalid fault request."
NODE_SCOPED_FAULTS = {
    FaultType.BELT_JAM,
    FaultType.MOTOR_OVERTEMP,
    FaultType.CONVEYOR_POWER_LOSS,
}
CONVEYOR_NODE_IDS = {"CNV-A", "CNV-B", "CNV-C"}
FAULT_NODE_PREFIXES = {
    "BELT_JAM_": FaultType.BELT_JAM,
    "MOTOR_OVERTEMP_": FaultType.MOTOR_OVERTEMP,
    "CONVEYOR_POWER_LOSS_": FaultType.CONVEYOR_POWER_LOSS,
}


@dataclass
class CommandError:
    code: str
    message: str
    status: int
    details: list[str] | None = None


def pallet_to_dict(pallet: Pallet) -> dict:
    return {
        "id": pallet.id,
        "position": list(pallet.position),
        "velocity": list(pallet.velocity),
        "state": pallet.state,
        "on_node": pallet.on_node,
        "weight_kg": pallet.weight_kg,
        "target_slot": pallet.target_slot,
    }


def build_state_snapshot(state_ref, all_nodes, plc, fault_injector, rack, scanner) -> dict:
    pallets = state_ref["pallets_ref"] or []
    tick = state_ref.get("tick", 0)
    return {
        "tick": tick,
        "timestamp": asyncio.get_running_loop().time(),
        "plc_state": plc.state,
        "pallets": [pallet_to_dict(pallet) for pallet in pallets],
        "nodes": {node_id: node.to_dict() for node_id, node in all_nodes.items()},
        "slots": rack.to_dict()["slots"],
        "faults_active": fault_injector.active_fault_names(),
        "alarms": plc.get_alarms(all_nodes, scanner),
    }


def build_http_error_response(error: CommandError):
    payload = {
        "error": {
            "code": error.code,
            "message": error.message,
        }
    }
    if error.details:
        payload["error"]["details"] = error.details
    return web.json_response(payload, status=error.status)


def build_command_error_payload(
    command: str | None,
    command_id: str | None,
    error: CommandError,
) -> dict:
    payload = {
        "type": "command_error",
        "command": command,
        "command_id": command_id,
        "code": error.code,
        "message": error.message,
    }
    if error.details:
        payload["details"] = error.details
    return payload


def build_fault_command_error(details: list[str], status: int = 400) -> CommandError:
    return CommandError(
        code="invalid_fault_request",
        message=FAULT_ERROR_MESSAGE,
        details=details,
        status=status,
    )


def validate_spawn_payload(data, rack):
    if not isinstance(data, dict):
        return None, None, CommandError(
            code="invalid_spawn_request",
            message="Invalid pallet spawn request.",
            details=["Request body must be a JSON object."],
            status=400,
        )

    errors = []
    weight = data.get("weight_kg", 100.0)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
        errors.append("weight_kg must be a positive number.")

    target_slot = data.get("target_slot")
    if target_slot is None:
        target_slot = rack.allocate_slot()
        if target_slot is None:
            return None, None, CommandError(
                code="spawn_unavailable",
                message="No rack slots are available.",
                status=409,
            )
    elif not isinstance(target_slot, str) or not rack.is_slot_available(target_slot):
        errors.append("target_slot must reference an available rack slot.")

    if errors:
        return None, None, CommandError(
            code="invalid_spawn_request",
            message="Invalid pallet spawn request.",
            details=errors,
            status=400,
        )

    return float(weight), target_slot, None


async def parse_spawn_request(request, rack):
    try:
        data = await request.json()
    except (json.JSONDecodeError, web.HTTPBadRequest):
        return None, None, build_http_error_response(
            CommandError(
                code="invalid_spawn_request",
                message="Invalid pallet spawn request.",
                details=["Request body must be valid JSON."],
                status=400,
            )
        )

    weight, target_slot, error = validate_spawn_payload(data, rack)
    if error is None:
        return weight, target_slot, None
    return None, None, build_http_error_response(error)


async def parse_json_object(request, *, allow_empty_body: bool = False):
    raw_body = await request.text()
    if not raw_body.strip():
        if allow_empty_body:
            return {}, None
        return None, build_fault_command_error(["Request body must be a JSON object."])

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return None, build_fault_command_error(["Request body must be valid JSON."])

    if not isinstance(data, dict):
        return None, build_fault_command_error(["Request body must be a JSON object."])

    return data, None


def normalize_fault_identifier(
    fault_type: str | None,
    node_id: str | None = None,
) -> tuple[str | None, str | None]:
    if not isinstance(fault_type, str):
        return fault_type, node_id

    normalized = fault_type.strip().upper()
    for prefix, mapped_fault in FAULT_NODE_PREFIXES.items():
        if normalized.startswith(prefix):
            target = normalized.removeprefix(prefix).replace("_", "-")
            return mapped_fault.value, target

    return normalized, node_id


def validate_fault_payload(
    data: dict,
    all_nodes: dict,
    *,
    allow_clear_all: bool = False,
):
    missing_fault_type = "fault_type" not in data or data.get("fault_type") is None
    if allow_clear_all and missing_fault_type:
        return None, None, None

    errors = []
    normalized_fault_type, node_id = normalize_fault_identifier(data.get("fault_type"), data.get("node_id"))
    fault = None

    if normalized_fault_type is None:
        errors.append("fault_type is required.")
    elif not isinstance(normalized_fault_type, str) or not normalized_fault_type.strip():
        errors.append("fault_type must be a non-empty string.")
    else:
        fault = FaultType.parse(normalized_fault_type)
        if fault is None:
            supported = ", ".join(fault_type.value for fault_type in FaultType)
            errors.append(f"fault_type must be one of: {supported}.")

    if node_id is not None and (not isinstance(node_id, str) or node_id not in all_nodes):
        errors.append("node_id must reference a known node.")

    if fault in NODE_SCOPED_FAULTS and node_id is not None and node_id not in CONVEYOR_NODE_IDS:
        errors.append("node_id must reference one of: CNV-A, CNV-B, CNV-C.")

    if errors:
        return None, None, build_fault_command_error(errors)

    return fault.value, node_id, None


def refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    state = build_state_snapshot(state_ref, all_nodes, plc, fault_injector, rack, scanner)
    state_ref["data"] = state
    return state


async def broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    state = refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
    await broadcast_state(state)
    return state


def create_nodes():
    cnv_a = ConveyorNode("CNV-A", length_m=4.0, speed_mps=0.5, direction=1)
    cnv_a.entry_x = 0.0
    cnv_a.exit_x = 4.0

    cnv_b = ConveyorNode("CNV-B", length_m=3.0, speed_mps=0.5, direction=1)
    cnv_b.entry_x = 4.0
    cnv_b.exit_x = 7.0

    cnv_c = ConveyorNode("CNV-C", length_m=3.0, speed_mps=0.5, direction=1)
    cnv_c.entry_x = 7.0
    cnv_c.exit_x = 10.0

    lift = LiftNode("LIFT-1")
    rack = StorageRack("RACK-1")
    scanner = SafetyScanner("SCAN-1")
    plc = CentralPLC()
    fault_injector = FaultInjector()

    all_nodes = {
        "CNV-A": cnv_a,
        "CNV-B": cnv_b,
        "CNV-C": cnv_c,
        "LIFT-1": lift,
        "RACK-1": rack,
        "SCAN-1": scanner,
    }
    return all_nodes, plc, fault_injector, rack, scanner


def sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets):
    fault_injector.apply_fault_effects(all_nodes, pallets)
    scanner.alarm_active = scanner.beam_broken or fault_injector.is_active(FaultType.LASER_BEAM_BLOCKED.value)

    if plc.check_estop(all_nodes, scanner):
        plc.state = "ESTOP"
        return

    if plc.state == "ESTOP":
        plc.reset()


def reset_simulation(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    pallets = state_ref["pallets_ref"]
    if pallets is None:
        pallets = []
        state_ref["pallets_ref"] = pallets
    else:
        pallets.clear()

    fault_injector.clear_all()
    plc.reset()
    rack.reset()
    state_ref["tick"] = 0

    for node in all_nodes.values():
        if hasattr(node, "reset"):
            node.reset()

    sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets)
    for node in all_nodes.values():
        if hasattr(node, "update"):
            node.update(0.0, pallets, all_nodes, fault_injector)

    return refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)


async def tick_loop(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    pallets: list[Pallet] = []
    tick = 0
    state_ref["pallets_ref"] = pallets

    while True:
        t0 = time.monotonic()

        sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets)
        if plc.state != "ESTOP":
            plc.update(TICK_DT, all_nodes, pallets, rack)

        for node in all_nodes.values():
            if hasattr(node, "update"):
                node.update(TICK_DT, pallets, all_nodes, fault_injector)

        for pallet in pallets:
            if pallet.state in ("moving", "transferring") and pallet.on_node:
                node = all_nodes.get(pallet.on_node)
                if node and hasattr(node, "move_pallet"):
                    node.move_pallet(pallet, TICK_DT)

        state_ref["tick"] = tick
        state = build_state_snapshot(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        state_ref["data"] = state

        await broadcast_state(state)
        tick += 1

        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, TICK_DT - elapsed))


async def main():
    logger.info("Starting Pallet Simulator Backend...")

    all_nodes, plc, fault_injector, rack, scanner = create_nodes()
    state_ref: dict = {"data": None, "pallets_ref": None, "tick": 0}

    async def handle_ws_command(websocket, payload):
        if not isinstance(payload, dict):
            error = CommandError(
                code="invalid_message",
                message="Command payload must be a JSON object.",
                status=400,
            )
            await send_message(websocket, build_command_error_payload(None, None, error))
            return

        command = payload.get("type")
        command_id = payload.get("command_id")

        if command == "spawn":
            weight, slot, error = validate_spawn_payload(payload, rack)
            if error is not None:
                await send_message(websocket, build_command_error_payload(command, command_id, error))
                return

            pallets = state_ref["pallets_ref"]
            if pallets is None:
                pallets = []
                state_ref["pallets_ref"] = pallets

            pallet = plc.spawn_pallet(weight, slot, pallets)
            await broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
            await send_message(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "command_id": command_id,
                    "message": f"Pallet {pallet.id} queued for {slot}.",
                },
            )
            return

        if command == "reset":
            reset_simulation(state_ref, all_nodes, plc, fault_injector, rack, scanner)
            await broadcast_state(state_ref["data"])
            await send_message(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "command_id": command_id,
                    "message": "Simulation reset.",
                },
            )
            return

        if command == "inject_fault":
            fault_type, node_id, error = validate_fault_payload(payload, all_nodes)
            if error is not None:
                await send_message(websocket, build_command_error_payload(command, command_id, error))
                return

            fault_injector.inject(fault_type, node_id)
            pallets = state_ref["pallets_ref"] or []
            sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets)
            await broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
            await send_message(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "command_id": command_id,
                    "message": f"Fault {fault_type} injected.",
                },
            )
            return

        if command == "clear_faults":
            fault_type, _, error = validate_fault_payload(payload, all_nodes, allow_clear_all=True)
            if error is not None:
                await send_message(websocket, build_command_error_payload(command, command_id, error))
                return

            if fault_type is None:
                fault_injector.clear_all()
            else:
                fault_injector.clear(fault_type)

            pallets = state_ref["pallets_ref"] or []
            sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets)
            await broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
            await send_message(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "command_id": command_id,
                    "message": "All faults cleared." if fault_type is None else f"Fault {fault_type} cleared.",
                },
            )
            return

        error = CommandError(
            code="unknown_command",
            message="Command type is not supported by the simulator.",
            status=400,
        )
        await send_message(websocket, build_command_error_payload(command, command_id, error))

    configure_websocket(on_message=handle_ws_command, get_state=lambda: state_ref["data"])
    tick_task = asyncio.create_task(tick_loop(state_ref, all_nodes, plc, fault_injector, rack, scanner))

    ws_port = 8765
    logger.info(f"WebSocket server on ws://0.0.0.0:{ws_port}")

    async def handle_state(request):
        if state_ref["data"] is None:
            return web.json_response({})
        return web.json_response(state_ref["data"].copy())

    async def handle_fault_inject(request):
        data, error = await parse_json_object(request)
        if error is not None:
            return build_http_error_response(error)

        fault_type, node_id, error = validate_fault_payload(data, all_nodes)
        if error is not None:
            return build_http_error_response(error)

        fault_injector.inject(fault_type, node_id)
        pallets = state_ref["pallets_ref"] or []
        sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets)
        refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"status": "ok", "faults_active": state_ref["data"]["faults_active"]})

    async def handle_fault_clear(request):
        data, error = await parse_json_object(request, allow_empty_body=True)
        if error is not None:
            return build_http_error_response(error)

        fault_type, _, error = validate_fault_payload(data, all_nodes, allow_clear_all=True)
        if error is not None:
            return build_http_error_response(error)

        if fault_type is None:
            fault_injector.clear_all()
        else:
            fault_injector.clear(fault_type)

        pallets = state_ref["pallets_ref"] or []
        sync_fault_state(all_nodes, plc, fault_injector, scanner, pallets)
        refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"status": "ok", "faults_active": state_ref["data"]["faults_active"]})

    async def handle_pallet_spawn(request):
        weight, slot, error_response = await parse_spawn_request(request, rack)
        if error_response is not None:
            return error_response

        pallets = state_ref["pallets_ref"]
        if pallets is None:
            pallets = []
            state_ref["pallets_ref"] = pallets

        pallet = plc.spawn_pallet(weight, slot, pallets)
        refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"id": pallet.id, "target_slot": slot})

    async def handle_reset(request):
        reset_simulation(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"status": "reset"})

    async def handle_health(request):
        state = state_ref["data"]
        if state is None:
            return web.json_response({"status": "starting"}, status=503)
        return web.json_response(
            {
                "status": "ok",
                "tick": state["tick"],
                "plc_state": state["plc_state"],
            }
        )

    app = web.Application()
    app.router.add_get("/api/state", handle_state)
    app.router.add_post("/api/fault/inject", handle_fault_inject)
    app.router.add_post("/api/fault/clear", handle_fault_clear)
    app.router.add_post("/api/pallet/spawn", handle_pallet_spawn)
    app.router.add_post("/api/reset", handle_reset)
    app.router.add_get("/api/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    logger.info("HTTP REST API on http://0.0.0.0:8000")

    try:
        async with websockets.serve(WebSocketHandler.handler, "0.0.0.0", ws_port):
            await tick_task
    finally:
        tick_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tick_task
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
