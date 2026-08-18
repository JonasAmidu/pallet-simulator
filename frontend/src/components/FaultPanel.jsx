import React from 'react'
import { useSimStore } from '../simulation/state'
import { isDemoMode, send } from '../simulation/SocketClient'
import { apiUrl } from '../simulation/network'

const FAULT_TYPES = [
  { id: 'BELT_JAM', nodeId: 'CNV-A', label: 'BELT_JAM (A)', group: 'Belt Jams' },
  { id: 'BELT_JAM', nodeId: 'CNV-B', label: 'BELT_JAM (B)', group: 'Belt Jams' },
  { id: 'BELT_JAM', nodeId: 'CNV-C', label: 'BELT_JAM (C)', group: 'Belt Jams' },
  { id: 'WEIGHT_OVERLOAD', label: 'WEIGHT_OVERLOAD', group: 'Load' },
  { id: 'LASER_BEAM_BLOCKED', label: 'LASER_BEAM_BLOCKED', group: 'Safety' },
  { id: 'MOTOR_OVERTEMP', nodeId: 'CNV-A', label: 'MOTOR_OVERTEMP (A)', group: 'Thermal' },
  { id: 'SLOT_CONFLICT', label: 'SLOT_CONFLICT', group: 'Storage' },
  { id: 'CONVEYOR_POWER_LOSS', nodeId: 'CNV-A', label: 'CONVEYOR_POWER_LOSS (A)', group: 'Power' },
]

async function injectFault(faultId, nodeId) {
  if (isDemoMode()) {
    send({ type: 'inject_fault', fault_type: faultId, node_id: nodeId })
    return
  }
  try {
    await fetch(apiUrl('/fault/inject'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fault_type: faultId, node_id: nodeId }),
    })
  } catch (e) {
    // Silently fail — WebSocket may handle it
    console.warn('Fault inject failed:', e)
  }
}

async function clearFaults() {
  if (isDemoMode()) {
    send({ type: 'clear_faults' })
    return
  }
  try {
    await fetch(apiUrl('/fault/clear'), {
      method: 'POST',
    })
  } catch (e) {
    console.warn('Fault clear failed:', e)
  }
}

export function FaultPanel() {
  const faults_active = useSimStore((s) => s.faults_active)
  const fault_targets = useSimStore((s) => s.fault_targets || {})

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
              const active = faults_active.includes(f.id) && (!f.nodeId || fault_targets[f.id] === f.nodeId)
              return (
                <button
                  key={`${f.id}-${f.nodeId || 'global'}`}
                  className={`fault-btn ${active ? 'active' : ''}`}
                  onClick={() => injectFault(f.id, f.nodeId)}
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
