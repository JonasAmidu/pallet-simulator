import { Canvas } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera } from '@react-three/drei'
import { Box, Line } from '@react-three/drei'
import { useSimStore } from '../simulation/state'
import { Conveyor } from './Conveyor'
import { Lift } from './Lift'
import { Rack } from './Rack'
import { Pallet } from './Pallet'

function Scene() {
  const pallets = useSimStore((s) => s.pallets)
  const nodes = useSimStore((s) => s.nodes)
  const slots = useSimStore((s) => s.slots)

  const liftLevel = nodes.LIFT_1?.level_m || 0

  return (
    <>
      {/* Camera */}
      <PerspectiveCamera makeDefault position={[15, 12, 15]} fov={50} />
      <OrbitControls target={[5, 1, 2]} enableDamping dampingFactor={0.05} />

      {/* Lighting */}
      <ambientLight intensity={0.4} />
      <directionalLight
        position={[10, 20, 10]}
        intensity={1.2}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-far={50}
        shadow-camera-left={-20}
        shadow-camera-right={20}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
      />
      <directionalLight position={[-5, 10, -5]} intensity={0.3} />
      <pointLight position={[5, 8, 0]} intensity={0.5} color="#fef3c7" />

      {/* Floor */}
      <Box args={[30, 0.1, 20]} position={[5, -0.05, 2]} receiveShadow>
        <meshStandardMaterial color="#1e293b" />
      </Box>

      {/* Floor grid lines */}
      <gridHelper args={[30, 30, '#334155', '#1e293b']} position={[5, 0.01, 2]} />

      {/* Walls */}
      {/* Back wall */}
      <Box args={[30, 6, 0.15]} position={[5, 3, -6]} castShadow receiveShadow>
        <meshStandardMaterial color="#1e293b" />
      </Box>
      {/* Left wall */}
      <Box args={[0.15, 6, 20]} position={[-7, 3, 2]} castShadow receiveShadow>
        <meshStandardMaterial color="#1e293b" />
      </Box>
      {/* Right wall */}
      <Box args={[0.15, 6, 20]} position={[17, 3, 2]} castShadow receiveShadow>
        <meshStandardMaterial color="#1e293b" />
      </Box>

      {/* Entry scanner - two posts with laser */}
      <group position={[0.5, 0, 1]}>
        {/* Left post */}
        <Box args={[0.08, 1.2, 0.08]} position={[-0.35, 0.6, 0]} castShadow>
          <meshStandardMaterial color="#334155" />
        </Box>
        {/* Right post */}
        <Box args={[0.08, 1.2, 0.08]} position={[0.35, 0.6, 0]} castShadow>
          <meshStandardMaterial color="#334155" />
        </Box>
        {/* Laser beam */}
        <Line
          points={[[-0.35, 0.9, 0], [0.35, 0.9, 0]]}
          color="#ef4444"
          lineWidth={2}
        />
        {/* Scanner heads */}
        <Box args={[0.12, 0.12, 0.12]} position={[-0.35, 1.0, 0]} castShadow>
          <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.5} />
        </Box>
        <Box args={[0.12, 0.12, 0.12]} position={[0.35, 1.0, 0]} castShadow>
          <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.5} />
        </Box>
      </group>

      {/* Conveyor A */}
      <Conveyor
        position={[2, 0.5, 1]}
        length={4}
        direction={1}
        node={nodes.CNV_A}
      />

      {/* Conveyor B */}
      <Conveyor
        position={[5.5, 0.5, 1]}
        length={3}
        direction={1}
        node={nodes.CNV_B}
      />

      {/* Conveyor C */}
      <Conveyor
        position={[9.5, 0.5, 1]}
        length={3}
        direction={1}
        node={nodes.CNV_C}
      />

      {/* Lift */}
      <Lift level={liftLevel} />

      {/* Rack */}
      <Rack slots={slots} />

      {/* Pallets */}
      {pallets.map((pallet) => (
        <Pallet key={pallet.id} pallet={pallet} />
      ))}
    </>
  )
}

export function Warehouse() {
  return (
    <Canvas
      shadows
      gl={{ antialias: true }}
      style={{ background: '#0d0d0d' }}
    >
      <Scene />
    </Canvas>
  )
}
