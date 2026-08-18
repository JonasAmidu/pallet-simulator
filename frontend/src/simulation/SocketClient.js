import { useSimStore } from './state.js'
import { DEMO_STATE } from './demoData.js'
import { shouldUseDemoMode, wsUrl } from './network.js'

let ws = null
let demoMode = false
let demoTick = 0
let demoInterval = null
let reconnectTimer = null
let manualClose = false
let commandSequence = 0
const pendingCommands = new Map()
const RECONNECT_DELAY_MS = 1000
let demoPallets = DEMO_STATE.pallets.map((pallet, index) => ({
  ...pallet,
  demoOffset: index * 2.5,
}))
let demoFaults = []
let demoFaultTargets = {}

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
      'LIFT-1': {
        ...DEMO_STATE.nodes['LIFT-1'],
        level_m: liftPallet ? liftPallet.position[1] - 0.65 : 0,
      },
    },
    faults_active: [...demoFaults],
    fault_targets: { ...demoFaultTargets },
    alarms: demoFaults.map((fault) => `${fault} active`),
    connected: false,
  }
  useSimStore.getState().setState(state)
  demoTick++
}

function rejectPendingCommands(message) {
  for (const { reject } of pendingCommands.values()) {
    reject(new Error(message))
  }
  pendingCommands.clear()
}

function scheduleReconnect() {
  if (reconnectTimer || manualClose || shouldUseDemoMode()) {
    return
  }
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, RECONNECT_DELAY_MS)
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

function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return
  }

  if (shouldUseDemoMode()) {
    useSimStore.getState().setConnectionStatus('disconnected')
    startDemoMode()
    return
  }

  manualClose = false
  useSimStore.getState().setConnectionStatus('reconnecting')
  const url = wsUrl()
  ws = new WebSocket(url)

  ws.onopen = () => {
    stopDemoMode()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    useSimStore.getState().setConnectionStatus('connected')
    console.log(`[Socket] Connected to ${url}`)
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'command_result') {
        const pending = pendingCommands.get(data.command_id)
        pendingCommands.delete(data.command_id)
        useSimStore.getState().setCommandFeedback({
          level: 'success',
          message: data.message,
          command: data.command,
        })
        pending?.resolve(data)
        return
      }

      if (data.type === 'command_error') {
        const pending = pendingCommands.get(data.command_id)
        pendingCommands.delete(data.command_id)
        const error = new Error(data.message)
        error.details = data.details || []
        error.code = data.code
        useSimStore.getState().setCommandFeedback({
          level: 'error',
          message: data.message,
          details: data.details || [],
          command: data.command,
        })
        pending?.reject(error)
        return
      }

      useSimStore.getState().setState(data)
    } catch (e) {
      console.warn('[Socket] Failed to parse message:', e)
    }
  }

  ws.onclose = () => {
    ws = null

    if (manualClose) {
      useSimStore.getState().setConnectionStatus('disconnected')
      rejectPendingCommands('Disconnected from simulator.')
      return
    }

    useSimStore.getState().setConnectionStatus('reconnecting')
    rejectPendingCommands('Connection to simulator lost while waiting for a response.')
    scheduleReconnect()
  }

  ws.onerror = (err) => {
    console.warn('[Socket] WebSocket error:', err)
  }
}

export function initSocket() {
  connect()
}

export function closeSocket() {
  manualClose = true
  stopDemoMode()
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    const socket = ws
    ws = null
    socket.close()
  } else {
    useSimStore.getState().setConnectionStatus('disconnected')
    rejectPendingCommands('Disconnected from simulator.')
  }
}

export const send = (data) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  } else {
    dispatchDemoAction(data)
  }
}

export function sendCommand(command) {
  if (demoMode || shouldUseDemoMode()) {
    dispatchDemoAction(command)
    useSimStore.getState().setCommandFeedback(null)
    return Promise.resolve({ type: 'command_result', command: command.type })
  }

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    const error = new Error('Simulator connection unavailable. Reconnect to send commands.')
    useSimStore.getState().setCommandFeedback({
      level: 'error',
      message: error.message,
      command: command.type,
    })
    return Promise.reject(error)
  }

  const command_id = `${command.type}-${++commandSequence}`
  const payload = { ...command, command_id }
  useSimStore.getState().setCommandFeedback(null)
  ws.send(JSON.stringify(payload))

  return new Promise((resolve, reject) => {
    pendingCommands.set(command_id, { resolve, reject })
  })
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
    demoFaultTargets = {}
    demoPallets = DEMO_STATE.pallets.slice(0, 3).map((pallet, index) => ({
      ...pallet,
      demoOffset: index * 2.5,
    }))
  } else if (data.type === 'inject_fault') {
    if (!demoFaults.includes(data.fault_type)) demoFaults.push(data.fault_type)
    if (data.node_id) demoFaultTargets[data.fault_type] = data.node_id
  } else if (data.type === 'clear_faults') {
    demoFaults = []
    demoFaultTargets = {}
  }

  applyDemoState()
}

export function isDemoMode() {
  return demoMode
}
