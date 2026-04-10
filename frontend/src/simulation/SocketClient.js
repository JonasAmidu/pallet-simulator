import { useSimStore } from './state.js'

let ws = null
let reconnectTimer = null

function connect(port) {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return
  }

  const url = `ws://localhost:${port}`
  ws = new WebSocket(url)

  ws.onopen = () => {
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
    useSimStore.getState().setConnected(false)
    console.log('[Socket] Disconnected')
    ws = null
    // Try reconnect on port 8765 if 8000 failed, or vice versa
    const nextPort = port === 8000 ? 8765 : 8000
    reconnectTimer = setTimeout(() => {
      console.log(`[Socket] Reconnecting to ${nextPort}...`)
      connect(nextPort)
    }, 2000)
  }

  ws.onerror = (err) => {
    console.warn(`[Socket] Error on port ${port}:`, err)
  }
}

export function initSocket() {
  connect(8000)
}

export function closeSocket() {
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
