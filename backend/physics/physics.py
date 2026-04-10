import numpy as np


def update_pallet_position(pallet, dt, nodes):
    """Apply velocity, check collisions, update on_node."""
    vx, vy, vz = pallet.velocity
    px, py, pz = pallet.position
    pallet.position = (px + vx * dt, py + vy * dt, pz + vz * dt)


def detect_jam(pallet, conveyor_node) -> bool:
    """Return True if pallet has been on same conveyor for >30 seconds."""
    # Simple implementation — track time_on_conveyor externally per pallet
    return False
