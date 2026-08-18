// Realistic demo state for when the backend is unavailable

const DEMO_TICK = 1247

export const DEMO_NODES = {
  'CNV-A': {
    belt_rpm: 450,
    motor_torque_nm: 12.3,
    photo_eye: true,
    weight_kg: 28.5,
    temperature_c: 42.1,
    position_mm: 2340,
    node_state: 'running',
  },
  'CNV-B': {
    belt_rpm: 450,
    motor_torque_nm: 10.8,
    photo_eye: false,
    weight_kg: 28.5,
    temperature_c: 39.7,
    position_mm: 1200,
    node_state: 'running',
  },
  'CNV-C': {
    belt_rpm: 300,
    motor_torque_nm: 8.2,
    photo_eye: false,
    weight_kg: 28.5,
    temperature_c: 36.4,
    position_mm: 800,
    node_state: 'running',
  },
  'LIFT-1': {
    level_m: 0.0,
    overload_kg: false,
    motor_torque_nm: 0.0,
    temperature_c: 38.9,
    level_encoder_pulses: 0,
    node_state: 'idle',
  },
  'RACK-1': {
    slots: [
      { id: 'SLOT-0-0', occupied: true, pallet_id: 'PLT-003' },
      { id: 'SLOT-0-1', occupied: true, pallet_id: 'PLT-007' },
      { id: 'SLOT-0-2', occupied: false, pallet_id: null },
      { id: 'SLOT-1-0', occupied: true, pallet_id: 'PLT-012' },
      { id: 'SLOT-1-1', occupied: false, pallet_id: null },
      { id: 'SLOT-1-2', occupied: true, pallet_id: 'PLT-002' },
      { id: 'SLOT-2-0', occupied: false, pallet_id: null },
      { id: 'SLOT-2-1', occupied: true, pallet_id: 'PLT-009' },
      { id: 'SLOT-2-2', occupied: false, pallet_id: null },
      { id: 'SLOT-3-0', occupied: true, pallet_id: 'PLT-001' },
      { id: 'SLOT-3-1', occupied: false, pallet_id: null },
      { id: 'SLOT-3-2', occupied: true, pallet_id: 'PLT-008' },
    ],
    node_state: 'running',
  },
  'SCAN-1': {
    beam_broken: false,
    temperature_c: 34.2,
    node_state: 'running',
  },
}

export const DEMO_PALLETS = [
  {
    id: 'PLT-001',
    position: [2.0, 0.15, 1.0],
    velocity: [0, 0, 0],
    weight_kg: 25.0,
    target_slot: 'SLOT-0-0',
    state: 'moving',
    on_node: 'CNV-A',
  },
  {
    id: 'PLT-002',
    position: [6.5, 0.15, 1.0],
    velocity: [0, 0, 0],
    weight_kg: 32.1,
    target_slot: 'SLOT-0-1',
    state: 'moving',
    on_node: 'CNV-B',
  },
  {
    id: 'PLT-003',
    position: [10.5, 0.15, 1.0],
    velocity: [0, 0, 0],
    weight_kg: 28.5,
    target_slot: 'SLOT-0-2',
    state: 'transferring',
    on_node: 'CNV-C',
  },
  {
    id: 'PLT-007',
    position: [0.5, 0.15, 0.8],
    velocity: [0, 0, 0],
    weight_kg: 22.3,
    target_slot: 'SLOT-1-0',
    state: 'stored',
    on_node: 'RACK-1',
  },
  {
    id: 'PLT-008',
    position: [1.5, 0.15, 0.8],
    velocity: [0, 0, 0],
    weight_kg: 30.0,
    target_slot: 'SLOT-1-1',
    state: 'stored',
    on_node: 'RACK-1',
  },
]

export const DEMO_STATE = {
  tick: DEMO_TICK,
  plc_state: 'TRANSPORTING',
  pallets: DEMO_PALLETS,
  nodes: DEMO_NODES,
  slots: DEMO_NODES['RACK-1'].slots,
  faults_active: [],
  alarms: [],
}
