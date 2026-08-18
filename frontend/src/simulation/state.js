import { create } from 'zustand'

export const useSimStore = create((set) => ({
  tick: 0,
  plc_state: 'IDLE',
  pallets: [],
  nodes: {},
  slots: [],
  faults_active: [],
  alarms: [],
  connected: false,
  connectionStatus: 'disconnected',
  commandFeedback: null,
  setState: (state) => set(state),
  setConnectionStatus: (connectionStatus) =>
    set({
      connectionStatus,
      connected: connectionStatus === 'connected',
    }),
  setCommandFeedback: (commandFeedback) => set({ commandFeedback }),
}))
