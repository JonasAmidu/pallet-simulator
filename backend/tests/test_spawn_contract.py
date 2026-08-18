import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from urllib import error, request


ROOT_DIR = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:8000"


def http_json(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    response = None
    try:
        response = request.urlopen(
            request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method),
            timeout=5,
        )
        status = response.status
        data = response.read()
    except error.HTTPError as exc:
        response = exc
        status = exc.code
        data = exc.read()
    finally:
        if response is not None:
            response.close()

    return status, json.loads(data.decode("utf-8"))


def wait_for_health(timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            status, _ = http_json("GET", "/api/health")
            if status == 200:
                return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(0.1)

    raise AssertionError(f"Backend did not become healthy within {timeout_seconds}s: {last_error!r}")


def wait_for_pallet(pallet_id: str, timeout_seconds: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status, state = http_json("GET", "/api/state")
        if status == 200:
            for pallet in state.get("pallets", []):
                if pallet.get("id") == pallet_id:
                    return pallet
        time.sleep(0.05)

    raise AssertionError(f"Pallet {pallet_id} did not appear in public state within {timeout_seconds}s")


class SpawnContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cls.backend = subprocess.Popen(
            ["python3", "backend/main.py"],
            cwd=ROOT_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_health()
        except Exception:
            cls.backend.terminate()
            cls.backend.wait(timeout=10)
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.backend.terminate()
        cls.backend.wait(timeout=10)

    def setUp(self) -> None:
        status, payload = http_json("POST", "/api/reset")
        self.assertEqual(status, 200, payload)

    def test_spawn_response_and_state_agree_on_identity_and_target_slot(self) -> None:
        status, spawn_payload = http_json(
            "POST",
            "/api/pallet/spawn",
            {"weight_kg": 142.5, "target_slot": "SLOT-2-1"},
        )

        self.assertEqual(status, 200, spawn_payload)
        self.assertIn("id", spawn_payload)
        self.assertEqual(spawn_payload.get("target_slot"), "SLOT-2-1")

        pallet = wait_for_pallet(spawn_payload["id"])
        self.assertEqual(pallet["id"], spawn_payload["id"])
        self.assertEqual(pallet["target_slot"], spawn_payload["target_slot"])

    def test_invalid_spawn_input_returns_stable_public_error(self) -> None:
        status, error_payload = http_json(
            "POST",
            "/api/pallet/spawn",
            {"weight_kg": 142.5, "target_slot": "SLOT-9-9"},
        )

        self.assertEqual(status, 400, error_payload)
        self.assertEqual(error_payload.get("error", {}).get("code"), "invalid_spawn_request")
        self.assertEqual(
            error_payload.get("error", {}).get("message"),
            "Invalid pallet spawn request.",
        )

    def test_back_to_back_default_spawns_reserve_distinct_slots(self) -> None:
        status, first_spawn = http_json("POST", "/api/pallet/spawn", {"weight_kg": 100.0})
        self.assertEqual(status, 200, first_spawn)

        status, second_spawn = http_json("POST", "/api/pallet/spawn", {"weight_kg": 110.0})
        self.assertEqual(status, 200, second_spawn)

        self.assertNotEqual(first_spawn["target_slot"], second_spawn["target_slot"])
        self.assertEqual(first_spawn["target_slot"], "SLOT-0-0")
        self.assertEqual(second_spawn["target_slot"], "SLOT-0-1")

    def test_explicit_spawn_cannot_reuse_a_reserved_slot(self) -> None:
        status, first_spawn = http_json(
            "POST",
            "/api/pallet/spawn",
            {"weight_kg": 100.0, "target_slot": "SLOT-1-0"},
        )
        self.assertEqual(status, 200, first_spawn)

        status, error_payload = http_json(
            "POST",
            "/api/pallet/spawn",
            {"weight_kg": 110.0, "target_slot": "SLOT-1-0"},
        )
        self.assertEqual(status, 400, error_payload)
        self.assertEqual(error_payload.get("error", {}).get("code"), "invalid_spawn_request")


if __name__ == "__main__":
    unittest.main()
