import { useSimStore } from '../simulation/state'

function valueClass(name, value) {
  if (value === undefined || value === null) return 'normal'
  if (name === 'belt_rpm') {
    if (value > 800) return 'alarm'
    if (value > 600) return 'warn'
    return 'normal'
  }
  if (name === 'temperature_c') {
    if (value > 80) return 'alarm'
    if (value > 60) return 'warn'
    return 'normal'
  }
  if (name === 'photo_eye') {
    return value ? 'on' : 'off'
  }
  if (name === 'overloaded') {
    return value ? 'alarm' : 'normal'
  }
  if (name === 'beam_broken') {
    return value ? 'alarm' : 'normal'
  }
  return 'normal'
}

function formatValue(name, value) {
  if (value === undefined || value === null) return '—'
  if (name === 'belt_rpm') return `${Math.round(value)} rpm`
  if (name === 'temperature_c') return `${value.toFixed(1)}°C`
  if (name === 'level_m') return `${value.toFixed(2)}m`
  if (name === 'photo_eye') return value ? 'ON' : 'OFF'
  if (name === 'overloaded') return value ? 'YES' : 'NO'
  if (name === 'beam_broken') return value ? 'YES' : 'NO'
  return String(value)
}

function sensorLabel(name) {
  const labels = {
    belt_rpm: 'Belt RPM',
    temperature_c: 'Temp',
    level_m: 'Level',
    photo_eye: 'Photo Eye',
    overloaded: 'Overload',
    beam_broken: 'Beam',
    state: 'State',
    fault: 'Fault',
  }
  return labels[name] || name
}

function NodeCard({ nodeId, node }) {
  const sensors = ['belt_rpm', 'temperature_c', 'level_m', 'photo_eye', 'overloaded', 'beam_broken']

  return (
    <div className="node-card">
      <div className="node-header">
        <span className="node-name">{nodeId}</span>
        <span className="node-type-badge">{node.type || nodeId.split('_')[0]}</span>
      </div>
      {node.state && (
        <div className="sensor-row">
          <span className="sensor-name">State</span>
          <span className={`sensor-value ${node.state === 'error' ? 'alarm' : 'normal'}`}>
            {node.state.toUpperCase()}
          </span>
        </div>
      )}
      {sensors.map((key) => {
        if (node[key] === undefined || node[key] === null) return null
        return (
          <div key={key} className="sensor-row">
            <span className="sensor-name">{sensorLabel(key)}</span>
            <span className={`sensor-value ${valueClass(key, node[key])}`}>
              {formatValue(key, node[key])}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function Telemetry() {
  const nodes = useSimStore((s) => s.nodes)
  const alarms = useSimStore((s) => s.alarms)

  const nodeEntries = Object.entries(nodes)

  return (
    <div className="telemetry-panel">
      <div className="telemetry-title">Telemetry</div>
      {nodeEntries.length === 0 ? (
        <div style={{ padding: '12px', color: '#555', fontSize: '12px' }}>
          Waiting for data...
        </div>
      ) : (
        <>
          {nodeEntries.map(([id, node]) => (
            <NodeCard key={id} nodeId={id} node={node} />
          ))}
          {alarms.length > 0 && (
            <div className="alarms-section">
              <div className="telemetry-title" style={{ borderBottom: 'none', paddingBottom: '4px' }}>
                Alarms
              </div>
              {alarms.map((alarm, i) => (
                <div key={i} className="alarm-item">
                  ⚠ {alarm}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
