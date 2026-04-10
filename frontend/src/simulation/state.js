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
  setState: (state) => set(state),
  setConnected: (v) => set({ connected: v }),
}))
