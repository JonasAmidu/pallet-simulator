import json
import os
import subprocess
import time
import unittest
from copy import deepcopy
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


def wait_for_state(predicate, timeout_seconds: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        status, state = http_json("GET", "/api/state")
        if status == 200:
            last_state = state
            if predicate(state):
                return state
        time.sleep(0.05)

    raise AssertionError(f"Expected public state was not observed within {timeout_seconds}s: {last_state!r}")


def normalized_state(state: dict) -> dict:
    snapshot = deepcopy(state)
    snapshot.pop("tick", None)
    snapshot.pop("timestamp", None)
    return snapshot


class ResetContractTest(unittest.TestCase):
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

    def test_reset_restores_a_repeatable_idle_baseline_after_movement_and_estop(self) -> None:
        baseline = normalized_state(
            wait_for_state(
                lambda state: (
                    state.get("plc_state") == "IDLE"
                    and state.get("pallets") == []
                    and state.get("faults_active") == []
                    and state.get("alarms") == []
                    and state.get("nodes", {}).get("SCAN-1", {}).get("beam_broken") is False
                    and state.get("nodes", {}).get("SCAN-1", {}).get("alarm_active") is False
                )
            )
        )

        status, spawn_payload = http_json(
            "POST",
            "/api/pallet/spawn",
            {"weight_kg": 125.0, "target_slot": "SLOT-2-1"},
        )
        self.assertEqual(status, 200, spawn_payload)

        moved_state = wait_for_state(
            lambda state: (
                len(state.get("pallets", [])) == 1
                and state.get("pallets", [{}])[0].get("on_node") == "CNV-A"
                and state.get("pallets", [{}])[0].get("position", [0.0])[0] > 0.0
                and state.get("nodes", {}).get("CNV-A", {}).get("position_mm", 0) > 0
                and state.get("plc_state") in {"LOADING", "TRANSPORTING", "LIFTING", "STORING", "COMPLETE"}
            )
        )
        self.assertEqual(moved_state["pallets"][0]["id"], spawn_payload["id"])

        status, payload = http_json("POST", "/api/fault/inject", {"fault_type": "LASER_BEAM_BLOCKED"})
        self.assertEqual(status, 200, payload)

        estop_state = wait_for_state(
            lambda state: (
                state.get("plc_state") == "ESTOP"
                and state.get("faults_active") == ["LASER_BEAM_BLOCKED"]
                and state.get("alarms") == ["LASER_ALARM"]
                and state.get("nodes", {}).get("SCAN-1", {}).get("beam_broken") is True
                and state.get("nodes", {}).get("SCAN-1", {}).get("alarm_active") is True
            )
        )
        self.assertEqual(estop_state["faults_active"], ["LASER_BEAM_BLOCKED"])

        status, reset_payload = http_json("POST", "/api/reset")
        self.assertEqual(status, 200, reset_payload)
        self.assertEqual(reset_payload, {"status": "reset"})

        first_reset_state = wait_for_state(lambda state: normalized_state(state) == baseline)
        self.assertEqual(normalized_state(first_reset_state), baseline)

        status, reset_payload = http_json("POST", "/api/reset")
        self.assertEqual(status, 200, reset_payload)
        self.assertEqual(reset_payload, {"status": "reset"})

        second_reset_state = wait_for_state(lambda state: normalized_state(state) == baseline)
        self.assertEqual(normalized_state(second_reset_state), baseline)


if __name__ == "__main__":
    unittest.main()
