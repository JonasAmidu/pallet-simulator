# Pallet Movement Simulator — Project Spec

## Overview

Real-time 3D warehouse simulation of a pallet transport system. Engineers use a visually-guided interface to monitor and interact with simulated machinery — conveyor belts, a lift, storage rack, safety scanners, and a central PLC coordinating everything over a simulated industrial bus.

Stack: **Python (asyncio) backend** + **Three.js/React frontend**

---

## Directory Structure

```
pallet-simulator/
├── backend/
│   ├── main.py              ← entry point, asyncio event loop
│   ├── models/
│   │   ├── __init__.py
│   │   ├── pallet.py        ← Pallet dataclass
│   │   ├── conveyor.py       ← ConveyorNode class
│   │   ├── lift.py           ← LiftNode class
│   │   ├── rack.py           ← StorageRack class
│   │   ├── scanner.py        ← SafetyScanner class
│   │   └── plc.py            ← CentralPLC class
│   ├── physics/
│   │   ├── __init__.py
│   │   └── physics.py        ← Physics engine (position, velocity, jam detection)
│   ├── bus/
│   │   ├── __init__.py
│   │   └── modbus.py         ← Simulated Modbus-like message bus
│   ├── faults/
│   │   ├── __init__.py
│   │   └── injector.py       ← Fault injection logic
│   ├── api/
│   │   ├── __init__.py
│   │   └── websocket.py      ← WebSocket server → frontend
│   └── requirements.txt
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.jsx           ← main React component
│   │   ├── App.css
│   │   ├── components/
│   │   │   ├── Warehouse.jsx  ← Three.js scene
│   │   │   ├── Pallet.jsx     ← animated pallet mesh
│   │   │   ├── Conveyor.jsx   ← conveyor segment mesh
│   │   │   ├── Lift.jsx       ← lift platform mesh
│   │   │   ├── Rack.jsx       ← storage rack mesh
│   │   │   ├── Telemetry.jsx  ← live sensor readout panel
│   │   │   └── FaultPanel.jsx ← fault injection controls
│   │   ├── simulation/
│   │   │   ├── SocketClient.js ← WebSocket → backend
│   │   │   └── state.js        ← shared sim state
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
├── README.md
└── SPEC.md
```

---

## Backend Specification

### Simulator Ticks
- Runs at 60 Hz (16.67ms per tick)
- Each tick: physics → sensors → PLC logic → broadcast state

### Pallet
```python
@dataclass
class Pallet:
    id: str
    position: tuple[float, float, float]   # (x, y, z) meters
    velocity: tuple[float, float, float]  # m/s
    weight_kg: float
    target_slot: str | None
    state: Literal['idle','moving','transferring','stored','error']
    on_node: str | None   # node id pallet is currently on
```

### Nodes

**ConveyorNode**
- Properties: `length_m`, `width_m`, `speed_mps`, `angle_deg`, `direction`
- Sensors: `belt_rpm`, `motor_torque_nm`, `photo_eye`, `weight_kg`, `temperature_c`, `position_mm`
- Commands: `start()`, `stop()`, `set_speed(speed_mps)`
- Physics: moves pallets at `speed_mps` along conveyor axis

**LiftNode**
- Properties: `min_level_m`, `max_level_m`, `current_level_m`, `capacity_kg`
- Sensors: `level_m`, `overload_kg`, `motor_torque_nm`, `temperature_c`, `level_encoder_pulses`
- Commands: `go_to_level(m)`, `emergency_stop()`
- Faults: overload → refuse to rise; level mismatch → alarm

**StorageRack**
- 3×4 grid = 12 slots
- Properties: `slots[12]` each with `occupied: bool`, `pallet_id: str|None`
- Sensors: per-slot IR sensor, total occupied count

**SafetyScanner**
- Laser curtain at entry zone
- Sensors: `beam_broken`, `alarm_active`
- Faults: beam_blocked → triggers e-stop across all nodes

**CentralPLC**
- Polls all nodes every 100ms via simulated Modbus
- State machine: `IDLE → LOADING → TRANSPORTING → STORING → COMPLETE`
- Broadcasts combined system state to frontend via WebSocket

### Modbus Bus (Simulated)
- All nodes register on a shared `Bus` object
- PLC sends read/write commands each tick
- Messages: `{from, to, func_code, address, value, timestamp}`

### Fault Injection
Injected via backend API or frontend panel:
- `BELT_JAM` — force conveyor RPM → 0, next pallet accumulates
- `WEIGHT_OVERLOAD` — pallet weight > lift capacity
- `LASER_BEAM_BLOCKED` — trigger safety e-stop
- `MOTOR_OVERTEMP` — reduce conveyor speed by 50%
- `SLOT_CONFLICT` — two pallets target same slot
- `CONVEYOR_POWER_LOSS` — node powers off

### WebSocket API (backend → frontend)

Broadcast every tick (~16ms), payload:
```json
{
  "tick": 12345,
  "timestamp": "2026-04-10T20:10:00.000Z",
  "plc_state": "TRANSPORTING",
  "pallets": [
    {
      "id": "PLT-001",
      "position": [2.4, 0.0, 1.2],
      "state": "moving",
      "on_node": "CNV-A",
      "weight_kg": 120.5
    }
  ],
  "nodes": {
    "CNV-A": {
      "type": "conveyor",
      "belt_rpm": 450,
      "motor_torque_nm": 12.4,
      "photo_eye": false,
      "temperature_c": 45.2,
      "position_mm": 1200
    },
    "LIFT-1": {
      "type": "lift",
      "level_m": 3.5,
      "overload_kg": false,
      "motor_torque_nm": 0.0,
      "temperature_c": 38.0
    }
  },
  "slots": [
    {"id": "SLOT-0-0", "occupied": true, "pallet_id": "PLT-001"},
    ...
  ],
  "faults_active": ["LASER_BEAM_BLOCKED"],
  "alarms": ["LASER_ALARM"]
}
```

### REST API (backend HTTP)
```
GET  /api/state          ← current full state
POST /api/fault inject   ← {fault_type, node_id}
POST /api/fault clear    ← {fault_type, node_id}
POST /api/pallet/spawn   ← {weight_kg, target_slot}
POST /api/reset          ← reset simulation
GET  /api/health         ← heartbeat
```

The spawn endpoint returns `{id, target_slot}`. Its identity and target slot
are repeated in subsequent REST and WebSocket state payloads. Invalid bodies,
weights, or rack slots return HTTP 400 as
`{error: {code: "invalid_spawn", message: "..."}}`.

---

## Frontend Specification

### Visual Style
- Dark industrial aesthetic — deep grey (#1a1a1a) floor, steel conveyors, amber warning lights
- Camera: isometric perspective, user can orbit/zoom
- Fonts: monospace for telemetry readouts

### 3D Scene (Three.js)
- **Floor**: large flat mesh, subtle grid lines
- **Conveyors**: box geometry segments, animated belt texture (scrolling UV)
- **Lift**: platform that animates vertically between floor and upper level
- **Pallets**: box geometry with crates/boxes on top
- **Rack**: grid of shelf slots with LED indicators (green=empty, red=occupied)
- **Scanner**: laser curtain beams drawn as thin red lines across entry zone
- **Lighting**: ambient + directional from upper-left

### Telemetry Panel (overlay)
- Real-time readout: each node's key sensor values
- Color-coded: green (OK), amber (warning), red (alarm)
- Updates from WebSocket broadcast

### Fault Panel (overlay)
- Toggle switches for each fault type
- When active, fault shows in alarm list
- Reset button clears all active faults

### Control Panel
- "Spawn Pallet" button — creates a new pallet at entry
- "Reset Sim" button — resets everything
- "Emergency Stop" button — big red, triggers e-stop fault

### Pallet Color States
- `idle`: grey
- `moving`: amber glow
- `transferring`: blue
- `stored`: green
- `error`: red pulse

---

## Deployment

### Option A: Docker Compose (recommended)
```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000", "8765:8765"]  # 8000=HTTP, 8765=WebSocket
    restart: unless-stopped
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
```

### Option B: Local Dev
```bash
# backend
cd backend && pip install -r requirements.txt && python main.py

# frontend
cd frontend && npm install && npm run dev
```

---

## Success Criteria

- [ ] Pallet spawns at entry conveyor, moves to storage slot automatically
- [ ] Lift raises and lowers pallets between floor levels
- [ ] Safety scanner beam break triggers e-stop across all nodes
- [ ] Fault injection panel can trigger and clear each fault type
- [ ] Telemetry panel shows live sensor values from all nodes
- [ ] 3D visualization updates smoothly at >30 FPS
- [ ] Reset clears all pallets and returns system to IDLE
