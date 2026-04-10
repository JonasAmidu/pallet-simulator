import { Box } from '@react-three/drei'

const COLS = 3
const ROWS = 4
const CELL_W = 1.4
const CELL_H = 1.2
const START_X = 6.0
const START_Z = 1.5

export function Rack({ slots = [] }) {
  const slotMap = {}
  slots.forEach((s) => {
    slotMap[s.id] = s
  })

  return (
    <group position={[START_X, 0, START_Z]}>
      {/* Back panel */}
      <Box args={[CELL_W * COLS + 0.2, CELL_H * ROWS + 0.2, 0.06]} position={[0, (CELL_H * ROWS) / 2, 2]} castShadow receiveShadow>
        <meshStandardMaterial color="#1e293b" />
      </Box>

      {/* Vertical frames */}
      <Box args={[0.06, CELL_H * ROWS + 0.3, 0.06]} position={[-(CELL_W * COLS) / 2 - 0.03, (CELL_H * ROWS) / 2, 0]} castShadow>
        <meshStandardMaterial color="#334155" />
      </Box>
      <Box args={[0.06, CELL_H * ROWS + 0.3, 0.06]} position={[(CELL_W * COLS) / 2 + 0.03, (CELL_H * ROWS) / 2, 0]} castShadow>
        <meshStandardMaterial color="#334155" />
      </Box>

      {/* Shelves and LEDs */}
      {Array.from({ length: ROWS }).map((_, row) =>
        Array.from({ length: COLS }).map((_, col) => {
          const slotId = `RACK-${row}-${col}`
          const slot = slotMap[slotId]
          const occupied = slot?.occupied || false

          const x = -CELL_W * (COLS - 1) / 2 + col * CELL_W
          const y = 0.05 + row * CELL_H

          return (
            <group key={slotId} position={[x, y, 0]}>
              {/* Shelf */}
              <Box args={[CELL_W - 0.1, 0.04, 0.8]} receiveShadow castShadow>
                <meshStandardMaterial color="#475569" />
              </Box>
              {/* LED indicator */}
              <mesh position={[CELL_W / 2 - 0.15, 0.05, 0.3]}>
                <boxGeometry args={[0.08, 0.04, 0.04]} />
                <meshStandardMaterial
                  color={occupied ? '#ef4444' : '#22c55e'}
                  emissive={occupied ? '#ef4444' : '#22c55e'}
                  emissiveIntensity={0.8}
                />
              </mesh>
            </group>
          )
        })
      )}
    </group>
  )
}
