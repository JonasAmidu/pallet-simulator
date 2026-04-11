import { useSimStore } from './state.js'
import { DEMO_STATE } from './demoData.js'

let ws = null
let reconnectTimer = null
let demoMode = false
let demoTick = 0
let demoInterval = null

function applyDemoState() {
  const state = {
    ...DEMO_STATE,
    tick: demoTick,
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
    console.warn('[Socket] Cannot send, not connected')
  }
}
