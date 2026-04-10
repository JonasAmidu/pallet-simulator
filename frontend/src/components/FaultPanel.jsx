import { useSimStore } from '../simulation/state'

const FAULT_TYPES = [
  { id: 'BELT_JAM_CNV_A', label: 'BELT_JAM (A)', group: 'Belt Jams' },
  { id: 'BELT_JAM_CNV_B', label: 'BELT_JAM (B)', group: 'Belt Jams' },
  { id: 'BELT_JAM_CNV_C', label: 'BELT_JAM (C)', group: 'Belt Jams' },
  { id: 'WEIGHT_OVERLOAD', label: 'WEIGHT_OVERLOAD', group: 'Load' },
  { id: 'LASER_BEAM_BLOCKED', label: 'LASER_BEAM_BLOCKED', group: 'Safety' },
  { id: 'MOTOR_OVERTEMP', label: 'MOTOR_OVERTEMP', group: 'Thermal' },
  { id: 'SLOT_CONFLICT', label: 'SLOT_CONFLICT', group: 'Storage' },
  { id: 'CONVEYOR_POWER_LOSS', label: 'CONVEYOR_POWER_LOSS', group: 'Power' },
]

async function injectFault(faultId) {
  try {
    await fetch('http://localhost:8000/api/fault/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fault_type: faultId }),
    })
  } catch (e) {
    // Silently fail — WebSocket may handle it
    console.warn('Fault inject failed:', e)
  }
}

async function clearFaults() {
  try {
    await fetch('http://localhost:8000/api/fault/clear', {
      method: 'POST',
    })
  } catch (e) {
    console.warn('Fault clear failed:', e)
  }
}

export function FaultPanel() {
  const faults_active = useSimStore((s) => s.faults_active)

  const groups = FAULT_TYPES.reduce((acc, f) => {
    if (!acc[f.group]) acc[f.group] = []
    acc[f.group].push(f)
    return acc
  }, {})

  return (
    <div className="fault-panel">
      <div className="fault-title">Fault Injection</div>
      <div className="fault-buttons">
        {Object.entries(groups).map(([group, faults]) => (
          <div key={group}>
            <div className="fault-group-label">{group}</div>
            {faults.map((f) => {
              const active = faults_active.includes(f.id)
              return (
                <button
                  key={f.id}
                  className={`fault-btn ${active ? 'active' : ''}`}
                  onClick={() => injectFault(f.id)}
                >
                  {f.label}
                </button>
              )
            })}
          </div>
        ))}
      </div>
      <button className="clear-btn" onClick={clearFaults}>
        Clear All Faults
      </button>
    </div>
  )
}
