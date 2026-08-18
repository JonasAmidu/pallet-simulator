import asyncio
import contextlib
import json
import logging
import time

from aiohttp import web

from models.pallet import Pallet
from models.conveyor import ConveyorNode
from models.lift import LiftNode
from models.rack import StorageRack
from models.scanner import SafetyScanner
from models.plc import CentralPLC
from faults.injector import FaultInjector, FaultType
from api.websocket import broadcast_state, WebSocketHandler
import websockets

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
        "nodes": {
            node_id: node.to_dict() for node_id, node in all_nodes.items()
        },
        "slots": rack.to_dict()["slots"],
        "faults_active": [f for f, active in fault_injector.active_faults.items() if active],
        "alarms": plc.get_alarms(all_nodes, scanner),
    }


def spawn_error_response(message: str, details: list[str] | None = None, status: int = 400):
    payload = {
        "error": {
            "code": "invalid_spawn_request",
            "message": message,
        }
    }
    if details:
        payload["error"]["details"] = details
    return web.json_response(payload, status=status)


async def parse_spawn_request(request, rack):
    try:
        data = await request.json()
    except (json.JSONDecodeError, web.HTTPBadRequest):
        return None, None, spawn_error_response("Invalid pallet spawn request.", ["Request body must be valid JSON."])

    if not isinstance(data, dict):
        return None, None, spawn_error_response("Invalid pallet spawn request.", ["Request body must be a JSON object."])

    errors = []
    weight = data.get("weight_kg", 100.0)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
        errors.append("weight_kg must be a positive number.")

    target_slot = data.get("target_slot")
    if target_slot is None:
        target_slot = rack.allocate_slot()
        if target_slot is None:
            return None, None, web.json_response(
                {
                    "error": {
                        "code": "spawn_unavailable",
                        "message": "No rack slots are available.",
                    }
                },
                status=409,
            )
    elif not isinstance(target_slot, str) or not rack.is_slot_available(target_slot):
        errors.append("target_slot must reference an available rack slot.")

    if errors:
        return None, None, spawn_error_response("Invalid pallet spawn request.", errors)

    return float(weight), target_slot, None


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

        # Apply fault effects
        fault_injector.apply_fault_effects(all_nodes, pallets)

        # Update scanner alarm
        scanner.alarm_active = scanner.beam_broken or any(
            fault_injector.is_active(f) for f in [FaultType.LASER_BEAM_BLOCKED.value]
        )

        # If estop, halt everything
        if plc.check_estop(all_nodes, scanner):
            plc.state = "ESTOP"
        else:
            plc.update(TICK_DT, all_nodes, pallets, rack)

        # Update each node physics
        for node in all_nodes.values():
            if hasattr(node, "update"):
                node.update(TICK_DT, pallets, all_nodes, fault_injector)

        # Update pallet positions — move along conveyors
        for pallet in pallets:
            if pallet.state in ('moving', 'transferring') and pallet.on_node:
                node = all_nodes.get(pallet.on_node)
                if node and hasattr(node, 'move_pallet'):
                    still_on = node.move_pallet(pallet, TICK_DT)
                    if not still_on:
                        # Pallet has exited this node — PLC state machine handles next handoff
                        pass

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

    # Shared state reference for HTTP handlers
    state_ref: dict = {"data": None, "pallets_ref": None, "tick": 0}

    # Start tick loop in background
    tick_task = asyncio.create_task(tick_loop(state_ref, all_nodes, plc, fault_injector, rack, scanner))

    # WebSocket server
    ws_port = 8765
    logger.info(f"WebSocket server on ws://0.0.0.0:{ws_port}")

    # HTTP server for REST endpoints
    async def handle_state(request):
        if state_ref["data"] is None:
            return web.json_response({})
        return web.json_response(state_ref["data"].copy())

    async def handle_fault_inject(request):
        data = await request.json()
        fault_injector.inject(data["fault_type"], data.get("node_id"))
        return web.json_response({"status": "ok", "active_faults": fault_injector.active_faults})

    async def handle_fault_clear(request):
        data = await request.json()
        fault_injector.clear(data["fault_type"])
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
        state_ref["data"] = build_state_snapshot(state_ref, all_nodes, plc, fault_injector, rack, scanner)
        return web.json_response({"id": pallet.id, "target_slot": slot})

    async def handle_reset(request):
        pallets = state_ref["pallets_ref"]
        if pallets is not None:
            pallets.clear()
        fault_injector.clear_all()
        plc.state = "IDLE"
        rack.reset()
        # Reset all nodes
        for node in all_nodes.values():
            if hasattr(node, 'powered'):
                node.powered = True
            if hasattr(node, 'speed_mps'):
                if hasattr(node, '_target_speed'):
                    node.speed_mps = node._target_speed
            if hasattr(node, 'overload_kg'):
                node.overload_kg = False
        scanner.beam_broken = False
        scanner.alarm_active = False
        state_ref["data"] = build_state_snapshot(state_ref, all_nodes, plc, fault_injector, rack, scanner)
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
