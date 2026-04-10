import { useEffect, useRef, useState } from 'react'
import { initSocket, closeSocket } from './simulation/SocketClient'
import { useSimStore } from './simulation/state'
import { Warehouse } from './components/Warehouse'
import { Telemetry } from './components/Telemetry'
import { FaultPanel } from './components/FaultPanel'
import { ControlPanel } from './components/ControlPanel'

function StatusBar({ tick, plcState }) {
  const [fps, setFps] = useState(0)
  const lastTick = useRef(Date.now())
  const fpsFrames = useRef(0)

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now()
      const delta = now - lastTick.current
      setFps(Math.round((fpsFrames.current / delta) * 1000))
      fpsFrames.current = 0
      lastTick.current = now
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  fpsFrames.current++

  const stateClass = plcState?.toLowerCase() || 'idle'
  const isError = plcState?.toLowerCase().includes('error') || plcState?.toLowerCase().includes('fault')

  return (
    <div className="status-bar">
      <div className="status-item">
        <span className="status-label">PLC:</span>
        <span className={`status-value ${isError ? 'error' : stateClass}`}>
          {plcState || 'UNKNOWN'}
        </span>
      </div>
      <div className="status-item">
        <span className="status-label">Tick:</span>
        <span className="status-value">{tick}</span>
      </div>
      <div className="status-item">
        <span className="status-label">FPS:</span>
        <span className="status-value">{fps}</span>
      </div>
    </div>
  )
}

export default function App() {
  const tick = useSimStore((s) => s.tick)
  const plcState = useSimStore((s) => s.plc_state)
  const connected = useSimStore((s) => s.connected)
  const alarms = useSimStore((s) => s.alarms)
  const faults_active = useSimStore((s) => s.faults_active)

  useEffect(() => {
    initSocket()
    return () => closeSocket()
  }, [])

  const hasAlarms = alarms.length > 0

  return (
    <div className="app-layout">
      {/* Header */}
      <div className="header-bar">
        <div className="header-logo">
          <span>⚙</span> PalletSim
        </div>
        {hasAlarms && (
          <span className="alarm-item" style={{ marginLeft: '12px', fontSize: '11px' }}>
            ⚠ {alarms.length} ALARM{alarms.length > 1 ? 'S' : ''} ACTIVE
          </span>
        )}
        <div className="header-status">
          <span style={{ fontSize: '11px', color: faults_active.length > 0 ? '#ef4444' : '#555' }}>
            {faults_active.length > 0 ? `${faults_active.length} FAULT${faults_active.length > 1 ? 'S' : ''}` : 'No faults'}
          </span>
          <span>
            <span className={`connection-dot ${connected ? 'connected' : ''}`} />
            <span style={{ marginLeft: '5px' }}>{connected ? 'Connected' : 'Disconnected'}</span>
          </span>
        </div>
      </div>

      {/* Main area */}
      <div className="main-area">
        {/* Telemetry sidebar */}
        <Telemetry />

        {/* Canvas */}
        <div className="canvas-container">
          <Warehouse />

          {/* Control panel overlay */}
          <ControlPanel />

          {/* Fault panel overlay */}
          <FaultPanel />
        </div>
      </div>

      {/* Status bar */}
      <StatusBar tick={tick} plcState={plcState} />
    </div>
  )
}
