import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Box } from '@react-three/drei'

export function Lift({ level = 0 }) {
  const platformRef = useRef()

  useFrame(() => {
    if (platformRef.current) {
      platformRef.current.position.y = level + 0.05
    }
  })

  const railHeight = 4.5
  const shaftX = 6.5
  const shaftZ1 = 0.8
  const shaftZ2 = -0.8

  return (
    <group position={[shaftX, 0, 0]}>
      {/* Left rail */}
      <Box args={[0.06, railHeight, 0.06]} position={[0, railHeight / 2, shaftZ1]} castShadow>
        <meshStandardMaterial color="#666" />
      </Box>
      {/* Right rail */}
      <Box args={[0.06, railHeight, 0.06]} position={[0, railHeight / 2, shaftZ2]} castShadow>
        <meshStandardMaterial color="#666" />
      </Box>
      {/* Cross braces */}
      <Box args={[0.04, 0.04, Math.abs(shaftZ1 - shaftZ2)]} position={[0, 1, (shaftZ1 + shaftZ2) / 2]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>
      <Box args={[0.04, 0.04, Math.abs(shaftZ1 - shaftZ2)]} position={[0, 2.5, (shaftZ1 + shaftZ2) / 2]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>
      <Box args={[0.04, 0.04, Math.abs(shaftZ1 - shaftZ2)]} position={[0, 4, (shaftZ1 + shaftZ2) / 2]} castShadow>
        <meshStandardMaterial color="#555" />
      </Box>

      {/* Lift platform */}
      <group ref={platformRef}>
        <Box args={[1.5, 0.08, 1]} castShadow receiveShadow>
          <meshStandardMaterial color="#94a3b8" metalness={0.6} roughness={0.3} />
        </Box>
        {/* Platform edges */}
        <Box args={[1.5, 0.04, 0.04]} position={[0, 0.04, 0.5]} castShadow>
          <meshStandardMaterial color="#f97316" />
        </Box>
        <Box args={[1.5, 0.04, 0.04]} position={[0, 0.04, -0.5]} castShadow>
          <meshStandardMaterial color="#f97316" />
        </Box>
        <Box args={[0.04, 0.04, 1]} position={[0.73, 0.04, 0]} castShadow>
          <meshStandardMaterial color="#f97316" />
        </Box>
        <Box args={[0.04, 0.04, 1]} position={[-0.73, 0.04, 0]} castShadow>
          <meshStandardMaterial color="#f97316" />
        </Box>
      </group>
    </group>
  )
}
