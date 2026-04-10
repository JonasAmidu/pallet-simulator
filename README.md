# Pallet Movement Simulator

Real-time 3D warehouse simulation of an automated pallet transport system — for engineers to visually inspect, test fault conditions, and validate PLC logic before building physical machinery.

**Live (when deployed):** https://jonasamidu.github.io/pallet-simulator

---

## What It Simulates

A pallet enters at **Zone A**, travels along roller conveyors, is lifted to an upper level by an elevator, then transferred to an available slot in the storage rack at **Zone B**.

```
[Zone A]  ──conveyor──►  [Lift]  ──conveyor──►  [Zone B]
 Entry                     │                    Storage
                         ▼                   Rack (12 slots)
                   [PLC / Safety Scanner]
```

### Machines / PLC Nodes

| Node | Role | Key Sensors |
|------|------|------------|
| **Entry Conveyor (CNV-A)** | Feeds pallets into the system | Weight, photo-eye, belt RPM |
| **Conveyor Segment (CNV-B)** | Mid-transport | Belt RPM, jam detection |
| **Lift (LIFT-1)** | Raises pallets between floor levels | Level, overload, motor torque |
| **Storage Rack (RACK-1)** | 3×4 grid = 12 slots | Per-slot IR occupancy |
| **Safety Scanner (SCAN-1)** | Entry laser curtain | Beam broken → e-stop |
| **Central PLC** | Coordinates all nodes over Modbus bus | — |

---

## Features

### 🖥️ 3D Visualization (Three.js)
- Isometric warehouse view with animated conveyors, lift, and pallets
- Color-coded node states (green = OK, amber = warning, red = alarm)
- Animated belt textures, lift movement, pallet tracking
- Orbit camera controls

### 📡 Live Telemetry Panel
- Real-time sensor readouts for every node
- Temperature, RPM, torque, position, weight
- Color-coded thresholds

### ⚠️ Fault Injection Panel
Test real-world failure scenarios:
- **Belt Jam** — conveyor stalls, pallets accumulate
- **Weight Overload** — lift refuses to raise
- **Laser Beam Blocked** — system-wide emergency stop
- **Motor Overtemp** — conveyor slows to 50%
- **Slot Conflict** — two pallets target same rack slot
- **Power Loss** — node goes offline

### 🔄 Full PLC State Machine
```
IDLE → LOADING → TRANSPORTING → LIFTING → STORING → COMPLETE
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 / asyncio |
| Physics | NumPy (custom physics engine) |
| Communication | WebSocket (asyncio + websockets) |
| Frontend | React 18 / Vite |
| 3D | Three.js + @react-three/fiber |
| Visualization | CSS3 / HTML5 canvas |

---

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
python main.py
# Runs on ws://localhost:8765 + http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

### Docker
```bash
docker compose up --build
```

---

## API

### WebSocket (→ frontend)
Broadcasts full state every tick (~16ms):
```json
{
  "tick": 12345,
  "plc_state": "TRANSPORTING",
  "pallets": [{"id": "PLT-001", "position": [2.4, 0.0, 1.2], "state": "moving"}],
  "nodes": {"CNV-A": {"belt_rpm": 450, "temperature_c": 45.2}, ...},
  "faults_active": [],
  "alarms": []
}
```

### HTTP REST
```
POST /api/fault/inject   {fault_type, node_id}
POST /api/fault/clear    {fault_type}
POST /api/pallet/spawn   {weight_kg, target_slot}
POST /api/reset
GET  /api/state
```

---

## Project Structure

```
pallet-simulator/
├── backend/
│   ├── main.py
│   ├── models/       # Pallet, ConveyorNode, LiftNode, Rack, Scanner, PLC
│   ├── physics/      # Physics engine
│   ├── bus/         # Simulated Modbus
│   ├── faults/      # Fault injection
│   └── api/         # WebSocket + HTTP server
├── frontend/
│   ├── src/
│   │   ├── components/   # Warehouse, Telemetry, FaultPanel
│   │   └── simulation/   # WebSocket client, state
│   └── package.json
├── docker-compose.yml
├── SPEC.md
└── README.md
```
