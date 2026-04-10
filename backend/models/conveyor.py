from typing import Optional
from .pallet import Pallet


class ConveyorNode:
    def __init__(
        self,
        node_id: str,
        length_m: float = 4.0,
        width_m: float = 1.0,
        speed_mps: float = 0.5,
        angle_deg: float = 0.0,
        direction: int = 1,
    ):
        self.node_id = node_id
        self.length_m = length_m
        self.width_m = width_m
        self.speed_mps = speed_mps
        self.angle_deg = angle_deg
        self.direction = direction  # +1 or -1

        # Entry/exit positions in world coords (x-axis conveyors)
        self.entry_x = 0.0
        self.exit_x = length_m

        # Sensors
        self.belt_rpm: float = 0.0
        self.motor_torque_nm: float = 0.0
        self.photo_eye: bool = False
        self.weight_kg: float = 0.0
        self.temperature_c: float = 25.0
        self.position_mm: float = 0.0  # pallet position along conveyor axis
        self.powered: bool = True
        self._target_speed: float = speed_mps

    def start(self):
        self.powered = True

    def stop(self):
        self.powered = False
        self.belt_rpm = 0.0

    def set_speed(self, speed_mps: float):
        self._target_speed = speed_mps
        self.speed_mps = speed_mps

    def update(self, dt: float, pallets: list[Pallet], all_nodes: dict, fault_injector):
        """Update conveyor sensors and physics."""
        if self.powered:
            self.belt_rpm = (self.speed_mps / (2.0 * 3.14159265)) * 60.0 * self.direction
            self.motor_torque_nm = 10.0 + abs(self.speed_mps) * 5.0
            self.temperature_c = 25.0 + abs(self.speed_mps) * 20.0
        else:
            self.belt_rpm = 0.0
            self.motor_torque_nm = 0.0

    def move_pallet(self, pallet: Pallet, dt: float) -> bool:
        """
        Move pallet along conveyor if it's on this node.
        Returns True if pallet is still on this conveyor, False if it has exited.
        """
        if pallet.on_node != self.node_id:
            return True

        if not self.powered:
            return True

        # Update pallet position along conveyor axis
        new_x = pallet.position[0] + self.speed_mps * self.direction * dt
        pallet.position = (new_x, pallet.position[1], pallet.position[2])

        # Update position_mm
        self.position_mm = int((new_x - self.entry_x) * 1000.0)

        # Check photo-eye (at entry, ~0.2m from start)
        self.photo_eye = self.powered and (pallet.position[0] >= 0.2)

        # Check if pallet has exited the conveyor
        if self.direction == 1 and pallet.position[0] >= self.exit_x:
            # Pallet has reached end of conveyor
            return False
        elif self.direction == -1 and pallet.position[0] <= self.entry_x:
            return False

        return True

    def to_dict(self) -> dict:
        return {
            "type": "conveyor",
            "belt_rpm": round(self.belt_rpm, 2),
            "motor_torque_nm": round(self.motor_torque_nm, 2),
            "photo_eye": self.photo_eye,
            "temperature_c": round(self.temperature_c, 1),
            "position_mm": int(self.position_mm),
            "powered": self.powered,
            "speed_mps": self.speed_mps,
            "length_m": self.length_m,
        }
