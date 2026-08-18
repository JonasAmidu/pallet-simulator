import React from 'react'
import { Warehouse } from './components/Warehouse'
import { LiveSimulationApp } from './LiveSimulationApp'

export default function App() {
  return <LiveSimulationApp warehouse={<Warehouse />} />
}
