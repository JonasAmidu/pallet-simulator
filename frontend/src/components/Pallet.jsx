import { Box } from '@react-three/drei'

const STATE_COLORS = {
  idle: '#888888',
  moving: '#c8a97e',
  transferring: '#4a9eff',
  stored: '#4ade80',
  error: '#ef4444',
}

export function Pallet({ pallet }) {
  const state = pallet.state || 'idle'
  const color = STATE_COLORS[state] || STATE_COLORS.idle

  const position = pallet.position || [0, 0.1, 0]
  const [x, y, z] = Array.isArray(position) ? position : [position.x || 0, position.y || 0.1, position.z || 0]

  return (
    <group position={[x, y, z]}>
      {/* Pallet base */}
      <Box args={[0.8, 0.1, 0.6]} position={[0, 0.05, 0]} castShadow receiveShadow>
        <meshStandardMaterial color={color} />
      </Box>
      {/* Pallet deck boards */}
      <Box args={[0.8, 0.02, 0.08]} position={[0, 0.12, 0.2]} castShadow>
        <meshStandardMaterial color={color} />
      </Box>
      <Box args={[0.8, 0.02, 0.08]} position={[0, 0.12, 0]} castShadow>
        <meshStandardMaterial color={color} />
      </Box>
      <Box args={[0.8, 0.02, 0.08]} position={[0, 0.12, -0.2]} castShadow>
        <meshStandardMaterial color={color} />
      </Box>
      {/* Cargo box */}
      <Box
        args={[0.6, 0.3, 0.5]}
        position={[0, 0.28, 0]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color={color} opacity={0.9} transparent />
      </Box>
    </group>
  )
}
