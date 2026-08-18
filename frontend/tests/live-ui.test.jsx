import assert from 'node:assert/strict'
import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'

const { LiveSimulationApp } = await import('../src/LiveSimulationApp.jsx')
const { closeSocket, dispatchDemoAction } = await import('../src/simulation/SocketClient.js')
const { useSimStore } = await import('../src/simulation/state.js')

const BASE_STATE = {
  tick: 0,
  plc_state: 'IDLE',
  pallets: [],
  nodes: {},
  slots: [],
  faults_active: [],
  fault_targets: {},
  alarms: [],
}

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = FakeWebSocket.CONNECTING
    this.sent = []
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    FakeWebSocket.instances.push(this)
  }

  send(payload) {
    this.sent.push(JSON.parse(payload))
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code: 1000 })
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  message(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
}

function resetStore() {
  useSimStore.setState({
    ...BASE_STATE,
    connectionStatus: 'disconnected',
    commandFeedback: null,
    connected: false,
  })
}

function latestSocket() {
  return FakeWebSocket.instances.at(-1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function nodeText(node) {
  if (node === null || node === undefined) {
    return ''
  }
  if (typeof node === 'string') {
    return node
  }
  if (Array.isArray(node)) {
    return node.map(nodeText).join(' ')
  }
  return nodeText(node.children || [])
}

function renderedText(renderer) {
  return nodeText(renderer.toJSON()).replace(/\s+/g, ' ').trim()
}

function findButton(renderer, label) {
  return renderer.root.find(
    (node) => node.type === 'button' && nodeText(node.props.children).includes(label)
  )
}

async function withRenderedApp(run) {
  FakeWebSocket.instances = []
  globalThis.WebSocket = FakeWebSocket
  resetStore()

  let renderer
  await act(async () => {
    renderer = TestRenderer.create(
      <LiveSimulationApp warehouse={<div data-testid="warehouse-scene" />} />
    )
  })

  try {
    await run(renderer)
  } finally {
    await act(async () => {
      renderer.unmount()
      closeSocket()
      await sleep(0)
    })
    resetStore()
  }
}

async function testConnectionStates() {
  await withRenderedApp(async (renderer) => {
    assert.match(renderedText(renderer), /Reconnecting/)

    await act(async () => {
      latestSocket().open()
    })
    assert.match(renderedText(renderer), /Connected/)

    await act(async () => {
      latestSocket().close()
    })
    assert.match(renderedText(renderer), /Reconnecting/)

    await act(async () => {
      closeSocket()
      await sleep(0)
    })
    assert.match(renderedText(renderer), /Disconnected/)
  })
}

async function testResetUpdatesFromProtocol() {
  await withRenderedApp(async (renderer) => {
    await act(async () => {
      latestSocket().open()
      latestSocket().message({
        ...BASE_STATE,
        tick: 42,
        plc_state: 'TRANSPORTING',
        alarms: ['LASER alarm'],
        faults_active: ['LASER_BEAM_BLOCKED'],
      })
    })

    assert.match(renderedText(renderer), /TRANSPORTING/)
    assert.match(renderedText(renderer), /1 FAULT/)

    await act(async () => {
      findButton(renderer, 'Reset').props.onClick()
      await sleep(0)
    })

    const resetCommand = latestSocket().sent.at(-1)
    assert.equal(resetCommand.type, 'reset')
    assert.match(renderedText(renderer), /TRANSPORTING/)
    assert.match(renderedText(renderer), /1 FAULT/)

    await act(async () => {
      latestSocket().message({
        ...BASE_STATE,
        tick: 43,
        plc_state: 'IDLE',
      })
      latestSocket().message({
        type: 'command_result',
        command: 'reset',
        command_id: resetCommand.command_id,
        message: 'Simulation reset.',
      })
    })

    assert.match(renderedText(renderer), /IDLE/)
    assert.match(renderedText(renderer), /No faults/)
  })
}

async function testCommandFailureFeedback() {
  await withRenderedApp(async (renderer) => {
    const originalRandom = Math.random
    Math.random = () => 0

    try {
      await act(async () => {
        latestSocket().open()
      })

      await act(async () => {
        findButton(renderer, 'Spawn Pallet').props.onClick()
        await sleep(0)
      })

      const spawnCommand = latestSocket().sent.at(-1)
      assert.equal(spawnCommand.type, 'spawn')

      await act(async () => {
        latestSocket().message({
          type: 'command_error',
          command: 'spawn',
          command_id: spawnCommand.command_id,
          message: 'Spawn failed.',
          details: ['No rack slots are available.'],
        })
      })

      assert.match(renderedText(renderer), /Spawn failed\./)
      assert.match(renderedText(renderer), /No rack slots are available\./)
    } finally {
      Math.random = originalRandom
    }
  })
}

async function testNodeScopedFaultControlUsesAndHighlightsTarget() {
  await withRenderedApp(async (renderer) => {
    const requests = []
    const originalFetch = globalThis.fetch
    globalThis.fetch = async (url, options) => {
      requests.push({ url, options })
      return { ok: true }
    }

    try {
      await act(async () => {
        latestSocket().open()
        findButton(renderer, 'BELT_JAM (B)').props.onClick()
        await sleep(0)
      })

      assert.equal(requests.length, 1)
      assert.deepEqual(JSON.parse(requests[0].options.body), {
        fault_type: 'BELT_JAM',
        node_id: 'CNV-B',
      })

      await act(async () => {
        useSimStore.getState().setState({
          ...BASE_STATE,
          faults_active: ['BELT_JAM'],
          fault_targets: { BELT_JAM: 'CNV-B' },
        })
      })
      assert.match(findButton(renderer, 'BELT_JAM (B)').props.className, /active/)
      assert.doesNotMatch(findButton(renderer, 'BELT_JAM (A)').props.className, /active/)
    } finally {
      globalThis.fetch = originalFetch
    }
  })
}

async function testReconnectAfterUnexpectedClose() {
  await withRenderedApp(async (renderer) => {
    await act(async () => {
      latestSocket().open()
    })

    const initialSocket = latestSocket()
    await act(async () => {
      initialSocket.close()
    })

    assert.match(renderedText(renderer), /Reconnecting/)

    await sleep(1100)
    assert.equal(FakeWebSocket.instances.length, 2)
  })
}

async function testDemoStateMatchesBackendPublicShape() {
  resetStore()

  await act(async () => {
    dispatchDemoAction({ type: 'reset' })
    await sleep(0)
  })

  const state = useSimStore.getState()
  assert.ok(state.nodes['CNV-A'])
  assert.ok(state.nodes['LIFT-1'])
  assert.equal(state.slots[0]?.id, 'SLOT-0-0')
  assert.deepEqual(state.faults_active, [])
  assert.deepEqual(state.alarms, [])
  closeSocket()
}

const tests = [
  ['connection states', testConnectionStates],
  ['reset waits for protocol state', testResetUpdatesFromProtocol],
  ['command failure feedback', testCommandFailureFeedback],
  ['node-scoped fault target', testNodeScopedFaultControlUsesAndHighlightsTarget],
  ['automatic reconnect', testReconnectAfterUnexpectedClose],
  ['demo state matches backend public shape', testDemoStateMatchesBackendPublicShape],
]

let failures = 0

for (const [name, test] of tests) {
  try {
    await test()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures += 1
    console.error(`FAIL ${name}`)
    console.error(error)
  }
}

if (failures > 0) {
  process.exit(1)
}
