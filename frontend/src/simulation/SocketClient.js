import { useSimStore } from './state.js'
import { DEMO_STATE } from './demoData.js'

let ws = null
let reconnectTimer = null
let demoMode = false
let demoTick = 0
let demoInterval = null
let demoPallets = DEMO_STATE.pallets.map((pallet, index) => ({
  ...pallet,
  demoOffset: index * 2.5,
}))
let demoFaults = []

function movingPallet(pallet, index) {
  const progress = (demoTick * 0.08 + pallet.demoOffset) % 12
  const stopped = demoFaults.some((fault) =>
    fault.startsWith('BELT_JAM') || fault === 'LASER_BEAM_BLOCKED' || fault === 'CONVEYOR_POWER_LOSS'
  )
  const x = stopped ? pallet.position[0] : Math.min(11.5, 0.5 + progress)
  const onLift = x >= 6.1 && x <= 6.9
  const liftY = onLift ? Math.sin(((x - 6.1) / 0.8) * Math.PI) * 2.4 : 0
  return {
    ...pallet,
    id: pallet.id || `PLT-DEMO-${index}`,
    position: [x, 0.65 + liftY, 1],
    state: onLift ? 'transferring' : 'moving',
  }
}

function applyDemoState() {
  const pallets = demoPallets.map(movingPallet)
  const liftPallet = pallets.find((pallet) => pallet.position[1] > 0.65)
  const state = {
    ...DEMO_STATE,
    tick: demoTick,
    plc_state: demoFaults.length ? 'FAULT' : 'TRANSPORTING',
    pallets,
    nodes: {
      ...DEMO_STATE.nodes,
      LIFT_1: {
        ...DEMO_STATE.nodes.LIFT_1,
        level_m: liftPallet ? liftPallet.position[1] - 0.65 : 0,
      },
    },
    faults_active: [...demoFaults],
    alarms: demoFaults.map((fault) => `${fault} active`),
    connected: false,
  }
  useSimStore.getState().setState(state)
  demoTick++
}

function startDemoMode() {
  if (demoMode) return
  demoMode = true
  console.log('[Socket] Backend unavailable — starting demo mode')
  // Apply initial demo state
  applyDemoState()
  // Tick demo state every 500ms
  demoInterval = setInterval(applyDemoState, 500)
}

function stopDemoMode() {
  if (demoInterval) {
    clearInterval(demoInterval)
    demoInterval = null
  }
  demoMode = false
}

function connect(port) {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return
  }

  // Detect if we're on GitHub Pages (static hosting) — use demo mode
  const isStaticHost = !window.location.hostname.includes('localhost') &&
                       !window.location.hostname.includes('127.0.0.1')

  if (isStaticHost) {
    // Don't even try WebSocket on static hosting, go straight to demo
    startDemoMode()
    return
  }

  const url = `ws://localhost:${port}`
  ws = new WebSocket(url)

  // Timeout if connection takes too long (static hosts can't reach localhost)
  const connectTimeout = setTimeout(() => {
    if (ws && ws.readyState === WebSocket.CONNECTING) {
      ws.close()
      startDemoMode()
    }
  }, 2000)

  ws.onopen = () => {
    clearTimeout(connectTimeout)
    stopDemoMode()
    useSimStore.getState().setConnected(true)
    console.log(`[Socket] Connected to ${url}`)
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      useSimStore.getState().setState(data)
    } catch (e) {
      console.warn('[Socket] Failed to parse message:', e)
    }
  }

  ws.onclose = () => {
    clearTimeout(connectTimeout)
    useSimStore.getState().setConnected(false)
    ws = null
    // Try reconnect on alternate port once
    if (port === 8000) {
      setTimeout(() => connect(8765), 1000)
    } else {
      startDemoMode()
    }
  }

  ws.onerror = (err) => {
    clearTimeout(connectTimeout)
    console.warn(`[Socket] Error on port ${port}`)
  }
}

export function initSocket() {
  connect(8000)
}

export function closeSocket() {
  stopDemoMode()
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
}

export const send = (data) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  } else {
    dispatchDemoAction(data)
  }
}

export function dispatchDemoAction(data) {
  if (!demoMode) startDemoMode()

  if (data.type === 'spawn') {
    demoPallets.push({
      id: `PLT-${String(demoPallets.length + 1).padStart(3, '0')}`,
      position: [0.5, 0.65, 1],
      weight_kg: data.weight_kg || 100,
      state: 'moving',
      demoOffset: 0,
    })
  } else if (data.type === 'reset') {
    demoTick = 0
    demoFaults = []
    demoPallets = DEMO_STATE.pallets.slice(0, 3).map((pallet, index) => ({
      ...pallet,
      demoOffset: index * 2.5,
    }))
  } else if (data.type === 'inject_fault' && !demoFaults.includes(data.fault_type)) {
    demoFaults.push(data.fault_type)
  } else if (data.type === 'clear_faults') {
    demoFaults = []
  }

  applyDemoState()
}

export function isDemoMode() {
  return demoMode
}
