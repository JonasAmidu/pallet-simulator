from enum import Enum


class FaultType(Enum):
    BELT_JAM = "belt_jam"
    WEIGHT_OVERLOAD = "weight_overload"
    LASER_BEAM_BLOCKED = "laser_beam_blocked"
    MOTOR_OVERTEMP = "motor_overtemp"
    SLOT_CONFLICT = "slot_conflict"
    CONVEYOR_POWER_LOSS = "conveyor_power_loss"


class FaultInjector:
    def __init__(self):
        self.active_faults: dict[str, bool] = {f.value: False for f in FaultType}
        self.fault_details: dict[str, dict] = {}

    def inject(self, fault_type: str, node_id: str | None = None):
        self.active_faults[fault_type] = True
        self.fault_details[fault_type] = {"node_id": node_id}

    def clear(self, fault_type: str):
        self.active_faults[fault_type] = False
        if fault_type in self.fault_details:
            del self.fault_details[fault_type]

    def clear_all(self):
        self.active_faults = {f.value: False for f in FaultType}
        self.fault_details = {}

    def is_active(self, fault_type: str) -> bool:
        return self.active_faults.get(fault_type, False)

    def apply_fault_effects(self, nodes, pallets):
        # BELT_JAM → set conveyor.belt_rpm = 0 for target node
        if self.is_active(FaultType.BELT_JAM.value):
            target = self.fault_details.get(FaultType.BELT_JAM.value, {}).get("node_id")
            if target and target in nodes:
                node = nodes[target]
                if hasattr(node, 'belt_rpm'):
                    node.belt_rpm = 0.0
                    if hasattr(node, 'speed_mps'):
                        node.speed_mps = 0.0

        # WEIGHT_OVERLOAD → set overload_kg = True on lift
        if self.is_active(FaultType.WEIGHT_OVERLOAD.value):
            lift = nodes.get("LIFT-1")
            if lift and hasattr(lift, 'overload_kg'):
                lift.overload_kg = True

        # LASER_BEAM_BLOCKED → set scanner.beam_broken = True
        if self.is_active(FaultType.LASER_BEAM_BLOCKED.value):
            scanner = nodes.get("SCAN-1")
            if scanner and hasattr(scanner, 'beam_broken'):
                scanner.beam_broken = True

        # MOTOR_OVERTEMP → reduce conveyor speed by 50% on target node
        if self.is_active(FaultType.MOTOR_OVERTEMP.value):
            target = self.fault_details.get(FaultType.MOTOR_OVERTEMP.value, {}).get("node_id")
            if target and target in nodes:
                node = nodes[target]
                if hasattr(node, 'speed_mps'):
                    node.speed_mps = node._target_speed * 0.5 if hasattr(node, '_target_speed') else node.speed_mps * 0.5

        # CONVEYOR_POWER_LOSS → set conveyor.powered = False
        if self.is_active(FaultType.CONVEYOR_POWER_LOSS.value):
            target = self.fault_details.get(FaultType.CONVEYOR_POWER_LOSS.value, {}).get("node_id")
            if target and target in nodes:
                node = nodes[target]
                if hasattr(node, 'powered'):
                    node.powered = False
