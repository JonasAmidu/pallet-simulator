import asyncio
import logging
import time
import uuid
from datetime import datetime

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

        # Build state dict
        state = {
            "tick": tick,
            "timestamp": asyncio.get_event_loop().time(),
            "plc_state": plc.state,
            "pallets": [
                {
                    "id": p.id,
                    "position": list(p.position),
                    "velocity": list(p.velocity),
                    "state": p.state,
                    "on_node": p.on_node,
                    "weight_kg": p.weight_kg,
                    "target_slot": p.target_slot,
                }
                for p in pallets
            ],
            "nodes": {
                node_id: node.to_dict() for node_id, node in all_nodes.items()
            },
            "slots": rack.to_dict()["slots"],
            "faults_active": [f for f, active in fault_injector.active_faults.items() if active],
            "alarms": plc.get_alarms(all_nodes, scanner),
        }

        state_ref["data"] = state
        state_ref["pallets_ref"] = pallets

        await broadcast_state(state)
        tick += 1

        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, TICK_DT - elapsed))


async def main():
    logger.info("Starting Pallet Simulator Backend...")

    all_nodes, plc, fault_injector, rack, scanner = create_nodes()

    # Shared state reference for HTTP handlers
    state_ref: dict = {"data": None, "pallets_ref": None}

    # Start tick loop in background
    tick_task = asyncio.create_task(tick_loop(state_ref, all_nodes, plc, fault_injector, rack, scanner))

    # WebSocket server
    ws_port = 8765
    ws_server = websockets.serve(WebSocketHandler.handler, "0.0.0.0", ws_port)
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
        data = await request.json()
        pallets = state_ref["pallets_ref"]
        if pallets is None:
            pallets = []
        slot = data.get("target_slot") or rack.allocate_slot()
        p = plc.spawn_pallet(data.get("weight_kg", 100.0), slot, pallets)
        return web.json_response({"id": p.id, "slot": slot})

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
        return web.json_response({"status": "reset"})

    async def handle_health(request):
        return web.json_response({"status": "ok", "tick": 0})

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

    # Run both servers
    await asyncio.gather(tick_task, ws_server)


if __name__ == "__main__":
    asyncio.run(main())
