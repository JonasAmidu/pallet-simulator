import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Box, Cylinder } from '@react-three/drei'

const BELT_COLOR = '#1a1a1a'
const FRAME_COLOR = '#f97316'

export function Conveyor({ position, length = 3, direction = 1, node }) {
  const beltRef = useRef()
  const offsetRef = useRef(0)

  const beltRpm = node?.belt_rpm || 0

  useFrame((_, delta) => {
    if (beltRef.current) {
      offsetRef.current += beltRpm * delta * 0.01
      if (offsetRef.current > 1) offsetRef.current -= 1
      beltRef.current.material.map.offset.x = offsetRef.current
    }
  })

  return (
    <group position={position}>
      {/* Belt surface */}
      <Box
        ref={beltRef}
        args={[length, 0.05, 0.8]}
        position={[0, 0, 0]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color={BELT_COLOR} />
      </Box>

      {/* Belt stripes */}
      <mesh position={[0, 0.026, 0]}>
        <boxGeometry args={[length, 0.005, 0.02]} />
        <meshStandardMaterial color={FRAME_COLOR} />
      </mesh>

      {/* Frame - left rail */}
      <Box args={[length, 0.08, 0.04]} position={[0, 0.04, 0.42]} castShadow>
        <meshStandardMaterial color={FRAME_COLOR} />
      </Box>
      {/* Frame - right rail */}
      <Box args={[length, 0.08, 0.04]} position={[0, 0.04, -0.42]} castShadow>
        <meshStandardMaterial color={FRAME_COLOR} />
      </Box>
      {/* Frame - front leg */}
      <Box args={[0.05, 0.45, 0.05]} position={[length / 2 - 0.05, -0.225, 0.42]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>
      <Box args={[0.05, 0.45, 0.05]} position={[-length / 2 + 0.05, -0.225, 0.42]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>
      <Box args={[0.05, 0.45, 0.05]} position={[length / 2 - 0.05, -0.225, -0.42]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>
      <Box args={[0.05, 0.45, 0.05]} position={[-length / 2 + 0.05, -0.225, -0.42]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>

      {/* Direction arrow */}
      <mesh position={[0, 0.05, 0]} rotation={[0, direction > 0 ? 0 : Math.PI, 0]}>
        <coneGeometry args={[0.12, 0.3, 4]} />
        <meshStandardMaterial color={beltRpm > 0 ? '#22c55e' : '#444'} />
      </mesh>
    </group>
  )
}
