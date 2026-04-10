import uuid
from typing import Literal
from .pallet import Pallet
from .rack import StorageRack


class CentralPLC:
    STATES = Literal['IDLE', 'LOADING', 'TRANSPORTING', 'LIFTING', 'STORING', 'COMPLETE', 'ESTOP']

    def __init__(self):
        self.state: STATES = 'IDLE'
        self._tick_count = 0

    def spawn_pallet(self, weight_kg: float, target_slot: str, pallets: list[Pallet]) -> Pallet:
        """Create a new pallet at the entry conveyor."""
        p = Pallet(
            id=f"PLT-{uuid.uuid4().hex[:6].upper()}",
            position=(0.0, 0.0, 1.0),
            weight_kg=weight_kg,
            target_slot=target_slot,
            state='idle',
            on_node=None,
        )
        pallets.append(p)
        return p

    def reset(self):
        self.state = 'IDLE'
        self._tick_count = 0

    def check_estop(self, all_nodes: dict, scanner) -> bool:
        """Return True if any alarm is active."""
        if scanner.alarm_active:
            return True
        return False

    def get_alarms(self, all_nodes: dict, scanner) -> list[str]:
        """Return list of active alarm strings."""
        alarms = []
        if scanner.alarm_active:
            alarms.append("LASER_ALARM")
        # Check lift overload
        lift = all_nodes.get("LIFT-1")
        if lift and lift.overload_kg:
            alarms.append("LIFT_OVERLOAD")
        return alarms

    def update(self, dt: float, all_nodes: dict, pallets: list[Pallet], rack: StorageRack):
        """State machine update each tick."""
        self._tick_count += 1

        if self.state == 'ESTOP':
            # In e-stop, only allow reset via external call
            return

        if self.state == 'IDLE':
            # Look for a pallet that needs processing
            idle_pallets = [p for p in pallets if p.state in ('idle', 'moving') and p.on_node is None]
            if idle_pallets:
                self.state = 'LOADING'

        if self.state == 'LOADING':
            # Wait for pallet to be placed on entry conveyor
            cnv_a = all_nodes.get("CNV-A")
            if cnv_a:
                pallet_on_cnv = next((p for p in pallets if p.on_node == "CNV-A"), None)
                if pallet_on_cnv and cnv_a.position_mm > 200:
                    # Pallet has passed entry photo-eye
                    pallet_on_cnv.state = 'moving'
                    self.state = 'TRANSPORTING'

        elif self.state == 'TRANSPORTING':
            # Move pallet from CNV-A to CNV-B to lift entry
            cnv_a = all_nodes.get("CNV-A")
            cnv_b = all_nodes.get("CNV-B")
            pallet_on_cnv = next((p for p in pallets if p.on_node == "CNV-A"), None)
            if pallet_on_cnv:
                # Hand off from CNV-A to CNV-B when at exit
                if pallet_on_cnv.position[0] >= cnv_a.exit_x:
                    pallet_on_cnv.on_node = "CNV-B"
                    pallet_on_cnv.position = (cnv_b.entry_x, 0.0, 1.0)
                    cnv_b.position_mm = 0
                    pallet_on_cnv.state = 'transferring'
                    self.state = 'LIFTING'

        elif self.state == 'LIFTING':
            # Move pallet from CNV-B to lift, then lift to target level, then to CNV-C
            lift = all_nodes.get("LIFT-1")
            cnv_b = all_nodes.get("CNV-B")
            cnv_c = all_nodes.get("CNV-C")

            pallet_on_cnv = next((p for p in pallets if p.on_node == "CNV-B"), None)
            if pallet_on_cnv:
                if pallet_on_cnv.position[0] >= cnv_b.exit_x:
                    # Move onto lift
                    pallet_on_cnv.on_node = "LIFT-1"
                    pallet_on_cnv.position = (7.0, 0.0, 1.0)
                    pallet_on_cnv.state = 'transferring'

            pallet_on_lift = next((p for p in pallets if p.on_node == "LIFT-1"), None)
            if pallet_on_lift:
                # Determine target level from target_slot
                if pallet_on_lift.target_slot:
                    try:
                        parts = pallet_on_lift.target_slot.split('-')
                        row = int(parts[1])
                        target_level = row * 1.0
                    except Exception:
                        target_level = 0.0
                else:
                    target_level = 0.0

                lift.go_to_level(target_level)

                # Once lift reaches target level, deliver to CNV-C
                if not lift.moving and abs(lift.current_level_m - target_level) < 0.05:
                    pallet_on_lift.on_node = "CNV-C"
                    pallet_on_lift.position = (cnv_c.entry_x, lift.current_level_m, 1.0)
                    pallet_on_lift.state = 'transferring'
                    self.state = 'STORING'

        elif self.state == 'STORING':
            cnv_c = all_nodes.get("CNV-C")
            pallet_on_cnv = next((p for p in pallets if p.on_node == "CNV-C"), None)
            if pallet_on_cnv:
                if pallet_on_cnv.position[0] >= cnv_c.exit_x:
                    # Pallet reached end, store in rack
                    target = pallet_on_cnv.target_slot or rack.allocate_slot()
                    if target and rack.is_slot_available(target):
                        rack.occupy_slot(target, pallet_on_cnv.id)
                        slot_pos = rack.get_slot_position(target)
                        pallet_on_cnv.position = (slot_pos[0], slot_pos[1] + 0.5, slot_pos[2])
                        pallet_on_cnv.state = 'stored'
                        pallet_on_cnv.on_node = None
                        self.state = 'COMPLETE'

        elif self.state == 'COMPLETE':
            self.state = 'IDLE'
