import asyncio
import json
import sys
import unittest
from pathlib import Path

import aiohttp
import websockets


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from main import SimulatorServer


class PublicContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = SimulatorServer()
        await self.server.start(
            host="127.0.0.1",
            http_port=0,
            websocket_port=0,
        )
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close()
        await self.server.stop()

    async def test_spawned_pallet_is_observable_through_state_contract(self):
        async with websockets.connect(self.server.websocket_url) as websocket:
            response = await self.http.post(
                f"{self.server.http_url}/api/pallet/spawn",
                json={"weight_kg": 125.5, "target_slot": "SLOT-2-1"},
            )

            self.assertEqual(response.status, 200)
            spawn = await response.json()
            self.assertEqual(spawn["target_slot"], "SLOT-2-1")

            websocket_state = await asyncio.wait_for(
                self._state_containing(websocket, spawn["id"]),
                timeout=1,
            )

            response = await self.http.get(f"{self.server.http_url}/api/state")
            self.assertEqual(response.status, 200)
            rest_state = await response.json()

        for state in (websocket_state, rest_state):
            pallet = next(p for p in state["pallets"] if p["id"] == spawn["id"])
            self.assertEqual(pallet["target_slot"], spawn["target_slot"])
            self.assertEqual(pallet["position"], [0.0, 0.0, 1.0])
            self.assertEqual(state["plc_state"], "LOADING")

    async def test_invalid_spawn_returns_stable_public_error(self):
        invalid_requests = (
            (
                [],
                "request body must be a JSON object",
            ),
            (
                {"weight_kg": "heavy", "target_slot": "SLOT-2-1"},
                "weight_kg must be a positive number",
            ),
            (
                {"weight_kg": 0, "target_slot": "SLOT-2-1"},
                "weight_kg must be a positive number",
            ),
            (
                {"weight_kg": 100, "target_slot": "UNKNOWN"},
                "target_slot must identify an available rack slot",
            ),
        )

        for payload, message in invalid_requests:
            with self.subTest(payload=payload):
                response = await self.http.post(
                    f"{self.server.http_url}/api/pallet/spawn",
                    json=payload,
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(
                    await response.json(),
                    {"error": {"code": "invalid_spawn", "message": message}},
                )

        response = await self.http.get(f"{self.server.http_url}/api/health")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["status"], "ok")

    async def _state_containing(self, websocket, pallet_id):
        while True:
            state = json.loads(await websocket.recv())
            if any(pallet["id"] == pallet_id for pallet in state["pallets"]):
                return state
