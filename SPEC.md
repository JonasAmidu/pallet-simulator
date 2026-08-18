# Pallet Movement Simulator Spec

This document records the public behavior implemented in the repository as of the issue `#6` release work. It is intentionally narrower than an aspirational product spec and tracks the current code paths and verification surface.

## Runtime Topology

- `backend/main.py` starts an asyncio tick loop, an aiohttp REST server on `:8000`, and a WebSocket server on `:8765`.
- `frontend/` is a Vite app that talks to `/api/*` and `/ws` in local and Docker setups.
- `docker-compose.yml` runs the frontend behind nginx on `:8080`, proxying `/api/*` to `backend:8000` and `/ws` to `backend:8765`.
- GitHub Pages serves only the frontend build. In that environment the app falls back to demo mode and does not attempt to reach a live backend.

## Backend State Model

Every tick publishes a public snapshot with:

- `tick`: integer tick counter.
- `timestamp`: `asyncio.get_running_loop().time()` floating-point seconds.
- `plc_state`: one of `IDLE`, `LOADING`, `TRANSPORTING`, `LIFTING`, `STORING`, `COMPLETE`, `ESTOP`.
- `pallets`: public pallet list with `id`, `position`, `velocity`, `state`, `on_node`, `weight_kg`, `target_slot`.
- `nodes`: keyed by hyphenated node IDs such as `CNV-A`, `LIFT-1`, `SCAN-1`.
- `slots`: rack occupancy list keyed as `SLOT-r-c`.
- `faults_active`: active backend fault names.
- `alarms`: currently `LASER_ALARM` and `LIFT_OVERLOAD` when applicable.

## PLC Flow

The current PLC implementation moves pallets through this loop:

```text
IDLE -> LOADING -> TRANSPORTING -> LIFTING -> STORING -> COMPLETE -> IDLE
```

`ESTOP` is entered whenever the scanner alarm is active. The reset path or a cleared scanner fault returns the controller to its idle baseline.

## Public Commands

### REST

- `GET /api/health`
  Returns `503 {"status":"starting"}` until the first snapshot exists, then `200 {"status":"ok","tick":...,"plc_state":...}`.
- `GET /api/state`
  Returns the latest snapshot or `{}` during startup.
- `POST /api/pallet/spawn`
  Validates the JSON body, spawns a pallet, and returns `{"id": "...", "target_slot": "SLOT-r-c"}`.
- `POST /api/reset`
  Clears pallets, faults, rack occupancy, and node state; returns `{"status": "reset"}`.
- `POST /api/fault/inject`
  Accepts `fault_type` and optional `node_id`.
- `POST /api/fault/clear`
  Accepts an empty JSON object to clear everything or a `fault_type` to clear one fault.

Stable error payloads use:

```json
{
  "error": {
    "code": "invalid_spawn_request",
    "message": "Invalid pallet spawn request.",
    "details": ["weight_kg must be a positive number."]
  }
}
```

### WebSocket

- The backend sends the latest snapshot immediately after connect when one is available.
- Commands are JSON objects with a `type` and optional `command_id`.
- Supported command types are `spawn`, `reset`, `inject_fault`, and `clear_faults`.
- Command acknowledgements use either:

```json
{"type":"command_result","command":"reset","command_id":"reset-1","message":"Simulation reset."}
```

or

```json
{"type":"command_error","command":"spawn","command_id":"spawn-1","code":"spawn_unavailable","message":"No rack slots are available."}
```

## Frontend Behavior

- `LiveSimulationApp` renders telemetry, the warehouse canvas, the fault panel, the control panel, and a status bar.
- The Three.js scene reads the same hyphenated node IDs produced by the backend snapshots.
- Rack LEDs resolve against backend slot IDs of the form `SLOT-r-c`.
- The socket client automatically reconnects after unexpected close events.
- On `*.github.io`, the client switches to demo mode and synthesizes snapshots with the same public shape used by the live backend.

## CI and Verification Surface

- Backend behavioral coverage: `pytest backend/tests`
- Frontend interaction coverage: `cd frontend && npm test`
- Frontend production build: `cd frontend && npm run build`
- Local smoke verification: `./scripts/smoke-local.sh`
- Docker smoke verification: `./scripts/smoke-compose.sh`
- Generated-file hygiene: `./scripts/check-generated-files.sh`

GitHub Actions `ci.yml` runs the backend tests, frontend interaction tests, frontend build, local smoke script, generated-file check, and Docker smoke script.

## Trade-Offs

- The system is intentionally lightweight and stateful in memory. That makes local verification fast, but restart wipes simulation state.
- The frontend fault panel uses REST for fault mutations while the rest of the live control flow uses WebSocket commands. The UI still converges through the same public snapshot stream.
- The GitHub Pages deployment is optimized for an accessible demo, not a live industrial-control environment.

## Current Limitations

- There is no browser-driven end-to-end suite.
- The monotonic `timestamp` is not suitable for wall-clock audit trails.
- Fault modeling is intentionally partial; only the effects represented in `faults/injector.py` are simulated.
