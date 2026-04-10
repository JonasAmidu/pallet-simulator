import { send } from '../simulation/SocketClient'

async function spawnPallet() {
  const weight = Math.round(80 + Math.random() * 120)
  try {
    await fetch('http://localhost:8000/api/pallet/spawn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weight_kg: weight }),
    })
  } catch (e) {
    // Try via WebSocket
    send({ type: 'spawn', weight_kg: weight })
  }
}

async function resetSim() {
  try {
    await fetch('http://localhost:8000/api/reset', { method: 'POST' })
  } catch (e) {
    send({ type: 'reset' })
  }
}

function injectEStop() {
  send({ type: 'inject_fault', fault_type: 'LASER_BEAM_BLOCKED' })
}

export function ControlPanel() {
  return (
    <div className="control-panel">
      <button className="ctrl-btn spawn" onClick={spawnPallet}>
        + Spawn Pallet
      </button>
      <button className="ctrl-btn reset" onClick={resetSim}>
        Reset
      </button>
      <button className="ctrl-btn estop" onClick={injectEStop}>
        E-STOP
      </button>
    </div>
  )
}
