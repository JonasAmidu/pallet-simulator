import asyncio
import contextlib
import json
import logging
import math
import socket
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
    pallets: list[Pallet] = state_ref["pallets_ref"]
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
            update = getattr(node, "update", None)
            if update is not None:
                update(TICK_DT, pallets, all_nodes, fault_injector)

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


def create_http_app(state_ref, all_nodes, plc, fault_injector, rack, scanner):
    def invalid_spawn(message):
        return web.json_response(
            {"error": {"code": "invalid_spawn", "message": message}},
            status=400,
        )

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
        try:
            data = json.loads(await request.text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return invalid_spawn("request body must be a JSON object")

        if not isinstance(data, dict):
            return invalid_spawn("request body must be a JSON object")

        weight_kg = data.get("weight_kg", 100.0)
        if (
            isinstance(weight_kg, bool)
            or not isinstance(weight_kg, (int, float))
            or not math.isfinite(weight_kg)
            or weight_kg <= 0
        ):
            return invalid_spawn("weight_kg must be a positive number")

        pallets = state_ref["pallets_ref"]
        requested_slot = data.get("target_slot")
        if requested_slot is None:
            slot = rack.allocate_slot()
        elif isinstance(requested_slot, str) and rack.is_slot_available(requested_slot):
            slot = requested_slot
        else:
            return invalid_spawn("target_slot must identify an available rack slot")

        if slot is None:
            return invalid_spawn("target_slot must identify an available rack slot")

        p = plc.spawn_pallet(weight_kg, slot, pallets)
        return web.json_response({"id": p.id, "target_slot": slot})

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
    return app


class SimulatorServer:
    """Run the simulator's documented HTTP and WebSocket interfaces."""

    def __init__(self):
        (
            self.all_nodes,
            self.plc,
            self.fault_injector,
            self.rack,
            self.scanner,
        ) = create_nodes()
        self.state_ref = {"data": None, "pallets_ref": []}
        self.http_url = None
        self.websocket_url = None
        self._runner = None
        self._site = None
        self._ws_server = None
        self._tick_task = None

    async def start(self, host="0.0.0.0", http_port=8000, websocket_port=8765):
        app = create_http_app(
            self.state_ref,
            self.all_nodes,
            self.plc,
            self.fault_injector,
            self.rack,
            self.scanner,
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()

        http_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        http_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        http_socket.bind((host, http_port))
        actual_http_port = http_socket.getsockname()[1]
        self._site = web.SockSite(self._runner, http_socket)
        await self._site.start()

        self._ws_server = await websockets.serve(
            WebSocketHandler.handler,
            host,
            websocket_port,
        )
        actual_websocket_port = self._ws_server.sockets[0].getsockname()[1]
        client_host = "127.0.0.1" if host == "0.0.0.0" else host
        self.http_url = f"http://{client_host}:{actual_http_port}"
        self.websocket_url = f"ws://{client_host}:{actual_websocket_port}"

        self._tick_task = asyncio.create_task(
            tick_loop(
                self.state_ref,
                self.all_nodes,
                self.plc,
                self.fault_injector,
                self.rack,
                self.scanner,
            )
        )

    async def stop(self):
        if self._tick_task is not None:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task
            self._tick_task = None

        if self._ws_server is not None:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


async def main():
    logger.info("Starting Pallet Simulator Backend...")
    server = SimulatorServer()
    await server.start()
    logger.info("WebSocket server on %s", server.websocket_url)
    logger.info("HTTP REST API on %s", server.http_url)

    try:
        await asyncio.Future()
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
