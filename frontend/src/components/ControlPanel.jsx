import React from 'react'
import { useSimStore } from '../simulation/state'
import { sendCommand } from '../simulation/SocketClient'

async function spawnPallet() {
  const weight = Math.round(80 + Math.random() * 120)
  try {
    await sendCommand({ type: 'spawn', weight_kg: weight })
  } catch {
    // Feedback is already published through the shared store.
  }
}

async function resetSim() {
  try {
    await sendCommand({ type: 'reset' })
  } catch {
    // Feedback is already published through the shared store.
  }
}

function injectEStop() {
  void sendCommand({ type: 'inject_fault', fault_type: 'LASER_BEAM_BLOCKED' }).catch(() => {
    // Feedback is already published through the shared store.
  })
}

export function ControlPanel() {
  const commandFeedback = useSimStore((s) => s.commandFeedback)

  return (
    <div className="control-panel-wrap">
      <div className="control-panel">
        <button className="ctrl-btn spawn" onClick={() => void spawnPallet()}>
          + Spawn Pallet
        </button>
        <button className="ctrl-btn reset" onClick={() => void resetSim()}>
          Reset
        </button>
        <button className="ctrl-btn estop" onClick={injectEStop}>
          E-STOP
        </button>
      </div>
      {commandFeedback && (
        <div
          className={`command-feedback ${commandFeedback.level}`}
          role="status"
          aria-live="polite"
        >
          <span>{commandFeedback.message}</span>
          {commandFeedback.details?.length > 0 && (
            <span>{commandFeedback.details.join(' ')}</span>
          )}
        </div>
      )}
    </div>
  )
}
