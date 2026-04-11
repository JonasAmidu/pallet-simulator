// Realistic demo state for when the backend is unavailable

const DEMO_TICK = 1247

export const DEMO_NODES = {
  CNV_A: {
    belt_rpm: 450,
    motor_torque_nm: 12.3,
    photo_eye: true,
    weight_kg: 28.5,
    temperature_c: 42.1,
    position_mm: 2340,
    node_state: 'running',
  },
  CNV_B: {
    belt_rpm: 450,
    motor_torque_nm: 10.8,
    photo_eye: false,
    weight_kg: 28.5,
    temperature_c: 39.7,
    position_mm: 1200,
    node_state: 'running',
  },
  CNV_C: {
    belt_rpm: 300,
    motor_torque_nm: 8.2,
    photo_eye: false,
    weight_kg: 28.5,
    temperature_c: 36.4,
    position_mm: 800,
    node_state: 'running',
  },
  LIFT_1: {
    level_m: 0.0,
    overload_kg: false,
    motor_torque_nm: 0.0,
    temperature_c: 38.9,
    level_encoder_pulses: 0,
    node_state: 'idle',
  },
  RACK_1: {
    slots: [
      { id: 'SLOT_0', occupied: true, pallet_id: 'PLT-003' },
      { id: 'SLOT_1', occupied: true, pallet_id: 'PLT-007' },
      { id: 'SLOT_2', occupied: false, pallet_id: null },
      { id: 'SLOT_3', occupied: true, pallet_id: 'PLT-012' },
      { id: 'SLOT_4', occupied: false, pallet_id: null },
      { id: 'SLOT_5', occupied: true, pallet_id: 'PLT-002' },
      { id: 'SLOT_6', occupied: false, pallet_id: null },
      { id: 'SLOT_7', occupied: true, pallet_id: 'PLT-009' },
      { id: 'SLOT_8', occupied: false, pallet_id: null },
      { id: 'SLOT_9', occupied: true, pallet_id: 'PLT-001' },
      { id: 'SLOT_10', occupied: false, pallet_id: null },
      { id: 'SLOT_11', occupied: true, pallet_id: 'PLT-008' },
    ],
    node_state: 'running',
  },
  SCAN_1: {
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
    target_slot: 'SLOT_0',
    state: 'moving',
    on_node: 'CNV_A',
  },
  {
    id: 'PLT-002',
    position: [6.5, 0.15, 1.0],
    velocity: [0, 0, 0],
    weight_kg: 32.1,
    target_slot: 'SLOT_1',
    state: 'moving',
    on_node: 'CNV_B',
  },
  {
    id: 'PLT-003',
    position: [10.5, 0.15, 1.0],
    velocity: [0, 0, 0],
    weight_kg: 28.5,
    target_slot: 'SLOT_2',
    state: 'transferring',
    on_node: 'CNV_C',
  },
  {
    id: 'PLT-007',
    position: [0.5, 0.15, 0.8],
    velocity: [0, 0, 0],
    weight_kg: 22.3,
    target_slot: 'SLOT_3',
    state: 'stored',
    on_node: 'RACK_1',
  },
  {
    id: 'PLT-008',
    position: [1.5, 0.15, 0.8],
    velocity: [0, 0, 0],
    weight_kg: 30.0,
    target_slot: 'SLOT_4',
    state: 'stored',
    on_node: 'RACK_1',
  },
]

export const DEMO_STATE = {
  tick: DEMO_TICK,
  plc_state: 'TRANSPORTING',
  pallets: DEMO_PALLETS,
  nodes: DEMO_NODES,
  slots: DEMO_NODES.RACK_1.slots,
  faults_active: [],
  alarms: [],
}
