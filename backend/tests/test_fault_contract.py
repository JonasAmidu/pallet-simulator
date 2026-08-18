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


def wait_for_state(predicate, timeout_seconds: float = 5.0) -> dict:
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


class FaultContractTest(unittest.TestCase):
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

    def test_laser_fault_is_reflected_and_clears_from_public_state(self) -> None:
        status, payload = http_json("POST", "/api/fault/inject", {"fault_type": "LASER_BEAM_BLOCKED"})
        self.assertEqual(status, 200, payload)

        injected_state = wait_for_state(
            lambda state: (
                "LASER_BEAM_BLOCKED" in state.get("faults_active", [])
                and "LASER_ALARM" in state.get("alarms", [])
                and state.get("plc_state") == "ESTOP"
                and state.get("nodes", {}).get("SCAN-1", {}).get("beam_broken") is True
                and state.get("nodes", {}).get("SCAN-1", {}).get("alarm_active") is True
            )
        )
        self.assertEqual(injected_state["faults_active"], ["LASER_BEAM_BLOCKED"])
        self.assertEqual(injected_state["alarms"], ["LASER_ALARM"])

        status, payload = http_json("POST", "/api/fault/clear", {"fault_type": "LASER_BEAM_BLOCKED"})
        self.assertEqual(status, 200, payload)

        cleared_state = wait_for_state(
            lambda state: (
                state.get("faults_active") == []
                and state.get("alarms") == []
                and state.get("plc_state") == "IDLE"
                and state.get("nodes", {}).get("SCAN-1", {}).get("beam_broken") is False
                and state.get("nodes", {}).get("SCAN-1", {}).get("alarm_active") is False
            )
        )
        self.assertEqual(cleared_state["faults_active"], [])
        self.assertEqual(cleared_state["alarms"], [])

    def test_node_scoped_fault_requires_target_and_reports_it(self) -> None:
        status, error_payload = http_json("POST", "/api/fault/inject", {"fault_type": "MOTOR_OVERTEMP"})
        self.assertEqual(status, 400, error_payload)
        self.assertIn(
            "node_id is required for this fault type.",
            error_payload.get("error", {}).get("details", []),
        )

        status, payload = http_json(
            "POST",
            "/api/fault/inject",
            {"fault_type": "MOTOR_OVERTEMP", "node_id": "CNV-B"},
        )
        self.assertEqual(status, 200, payload)
        state = wait_for_state(lambda current: current.get("fault_targets", {}).get("MOTOR_OVERTEMP") == "CNV-B")
        self.assertEqual(state["faults_active"], ["MOTOR_OVERTEMP"])
        self.assertEqual(state["nodes"]["CNV-B"]["speed_mps"], 0.25)

    def test_invalid_fault_requests_return_useful_public_errors(self) -> None:
        cases = [
            ({}, "fault_type is required."),
            ({"fault_type": "NO_SUCH_FAULT"}, "fault_type must be one of:"),
        ]

        for payload, detail_prefix in cases:
            with self.subTest(payload=payload):
                status, error_payload = http_json("POST", "/api/fault/inject", payload)
                self.assertEqual(status, 400, error_payload)
                self.assertEqual(error_payload.get("error", {}).get("code"), "invalid_fault_request")
                self.assertEqual(error_payload.get("error", {}).get("message"), "Invalid fault request.")
                details = error_payload.get("error", {}).get("details", [])
                self.assertTrue(any(detail.startswith(detail_prefix) for detail in details), details)


if __name__ == "__main__":
    unittest.main()
