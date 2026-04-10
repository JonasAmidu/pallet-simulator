from .pallet import Pallet


class LiftNode:
    LIFT_SPEED_MPS = 0.5
    LEVEL_TOLERANCE_M = 0.05

    def __init__(
        self,
        node_id: str,
        min_level_m: float = 0.0,
        max_level_m: float = 4.0,
        capacity_kg: float = 500.0,
    ):
        self.node_id = node_id
        self.min_level_m = min_level_m
        self.max_level_m = max_level_m
        self.current_level_m: float = 0.0
        self.target_level_m: float = 0.0
        self.capacity_kg = capacity_kg

        # Sensors
        self.level_m: float = 0.0
        self.overload_kg: bool = False
        self.motor_torque_nm: float = 0.0
        self.temperature_c: float = 25.0
        self.level_encoder_pulses: int = 0
        self.moving: bool = False
        self.pallet_on_lift: bool = False

    def go_to_level(self, m: float):
        if self.min_level_m <= m <= self.max_level_m:
            self.target_level_m = m
        else:
            self.target_level_m = max(self.min_level_m, min(m, self.max_level_m))

    def emergency_stop(self):
        self.target_level_m = self.current_level_m
        self.moving = False

    def update(self, dt: float, pallets: list[Pallet], all_nodes: dict, fault_injector):
        """Update lift physics."""
        # Check for pallet on lift
        self.pallet_on_lift = any(
            p.on_node == self.node_id and p.state != 'stored'
            for p in pallets
        )

        # Check overload
        pallets_on_lift = [p for p in pallets if p.on_node == self.node_id and p.state != 'stored']
        total_weight = sum(p.weight_kg for p in pallets_on_lift)
        self.overload_kg = total_weight > self.capacity_kg

        # Move towards target
        if abs(self.target_level_m - self.current_level_m) > self.LEVEL_TOLERANCE_M:
            self.moving = True
            direction = 1 if self.target_level_m > self.current_level_m else -1
            delta = self.LIFT_SPEED_MPS * dt * direction
            new_level = self.current_level_m + delta

            # Clamp to target
            if direction == 1:
                new_level = min(new_level, self.target_level_m)
            else:
                new_level = max(new_level, self.target_level_m)

            self.current_level_m = new_level
            self.level_m = self.current_level_m
            self.level_encoder_pulses += int(abs(delta) * 1000)
            self.motor_torque_nm = 80.0 if self.overload_kg else 50.0
            self.temperature_c = 30.0 + abs(self.motor_torque_nm) * 0.5
        else:
            self.moving = False
            self.current_level_m = self.target_level_m
            self.level_m = self.current_level_m
            self.motor_torque_nm = 0.0 if not self.moving else self.motor_torque_nm

    def to_dict(self) -> dict:
        return {
            "type": "lift",
            "level_m": round(self.level_m, 3),
            "current_level_m": round(self.current_level_m, 3),
            "target_level_m": round(self.target_level_m, 3),
            "overload_kg": self.overload_kg,
            "motor_torque_nm": round(self.motor_torque_nm, 2),
            "temperature_c": round(self.temperature_c, 1),
            "level_encoder_pulses": self.level_encoder_pulses,
            "moving": self.moving,
            "pallet_on_lift": self.pallet_on_lift,
        }
