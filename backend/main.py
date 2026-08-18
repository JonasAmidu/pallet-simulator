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
KNOWN_FAULT_TYPES = {fault.value for fault in FaultType}


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
        "faults_active": [fault for fault, active in fault_injector.active_faults.items() if active],
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


def refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    state = build_state_snapshot(state_ref, all_nodes, plc, fault_injector, rack, scanner)
    state_ref["data"] = state
    return state


async def broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    state = refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
    await broadcast_state(state)
    return state


def reset_simulation(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    pallets = state_ref["pallets_ref"]
    if pallets is not None:
        pallets.clear()

    fault_injector.clear_all()
    plc.reset()
    rack.reset()

    for node in all_nodes.values():
        if hasattr(node, "powered"):
            node.powered = True
        if hasattr(node, "speed_mps") and hasattr(node, "_target_speed"):
            node.speed_mps = node._target_speed
        if hasattr(node, "overload_kg"):
            node.overload_kg = False

    scanner.beam_broken = False
    scanner.alarm_active = False
    return refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)


def normalize_fault_command(fault_type: str | None, node_id: str | None = None) -> tuple[str | None, str | None]:
    if not isinstance(fault_type, str):
        return None, None

    normalized = fault_type.strip()
    if normalized.startswith("BELT_JAM_"):
        target = normalized.removeprefix("BELT_JAM_").replace("_", "-")
        return FaultType.BELT_JAM.value, target

    normalized = normalized.lower()
    if normalized in KNOWN_FAULT_TYPES:
        return normalized, node_id

    return None, None


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


async def tick_loop(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    pallets: list[Pallet] = []
    tick = 0
    state_ref["pallets_ref"] = pallets

    while True:
        t0 = time.monotonic()

        fault_injector.apply_fault_effects(all_nodes, pallets)

        scanner.alarm_active = scanner.beam_broken or any(
            fault_injector.is_active(fault) for fault in [FaultType.LASER_BEAM_BLOCKED.value]
        )

        if plc.check_estop(all_nodes, scanner):
            plc.state = "ESTOP"
        else:
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
            fault_type, target_node_id = normalize_fault_command(payload.get("fault_type"), payload.get("node_id"))
            if fault_type is None:
                error = CommandError(
                    code="invalid_fault",
                    message="Fault command referenced an unknown fault type.",
                    status=400,
                )
                await send_message(websocket, build_command_error_payload(command, command_id, error))
                return

            fault_injector.inject(fault_type, target_node_id)
            await broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
            await send_message(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "command_id": command_id,
                    "message": f"Fault {payload.get('fault_type')} injected.",
                },
            )
            return

        if command == "clear_faults":
            fault_injector.clear_all()
            await broadcast_latest_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
            await send_message(
                websocket,
                {
                    "type": "command_result",
                    "command": command,
                    "command_id": command_id,
                    "message": "All faults cleared.",
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
        data = await request.json()
        fault_type, target_node_id = normalize_fault_command(data.get("fault_type"), data.get("node_id"))
        if fault_type is None:
            return build_http_error_response(
                CommandError(
                    code="invalid_fault",
                    message="Fault command referenced an unknown fault type.",
                    status=400,
                )
            )

        fault_injector.inject(fault_type, target_node_id)
        refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"status": "ok", "active_faults": fault_injector.active_faults})

    async def handle_fault_clear(request):
        try:
            data = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            data = {}

        fault_type, _ = normalize_fault_command(data.get("fault_type")) if data.get("fault_type") else (None, None)
        if fault_type is None:
            fault_injector.clear_all()
        else:
            fault_injector.clear(fault_type)

        refresh_state(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"status": "ok"})

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
