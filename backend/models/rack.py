class StorageRack:
    ROWS = 4
    COLS = 3

    def __init__(self, node_id: str = "RACK-1"):
        self.node_id = node_id
        # Slots indexed "SLOT-r-c"
        self.slots: dict[str, dict] = {}
        for row in range(self.ROWS):
            for col in range(self.COLS):
                slot_id = f"SLOT-{row}-{col}"
                self.slots[slot_id] = {
                    "occupied": False,
                    "pallet_id": None,
                    "row": row,
                    "col": col,
                    # Default position in world coords
                    "position": (6.0 + col * 1.2, 0.0, 2.0 + row * 1.0),
                }

    def allocate_slot(self) -> str | None:
        """Find first empty slot, return slot_id or None."""
        for slot_id, slot in self.slots.items():
            if not slot["occupied"]:
                return slot_id
        return None

    def release_slot(self, slot_id: str):
        if slot_id in self.slots:
            self.slots[slot_id]["occupied"] = False
            self.slots[slot_id]["pallet_id"] = None

    def is_slot_available(self, slot_id: str) -> bool:
        if slot_id not in self.slots:
            return False
        return not self.slots[slot_id]["occupied"]

    def occupy_slot(self, slot_id: str, pallet_id: str):
        if slot_id in self.slots:
            self.slots[slot_id]["occupied"] = True
            self.slots[slot_id]["pallet_id"] = pallet_id

    def get_slot_position(self, slot_id: str) -> tuple[float, float, float]:
        if slot_id in self.slots:
            return self.slots[slot_id]["position"]
        return (0.0, 0.0, 0.0)

    def reset(self):
        for slot in self.slots.values():
            slot["occupied"] = False
            slot["pallet_id"] = None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "slots": [
                {
                    "id": slot_id,
                    "occupied": slot["occupied"],
                    "pallet_id": slot["pallet_id"],
                    "row": slot["row"],
                    "col": slot["col"],
                    "position": list(slot["position"]),
                }
                for slot_id, slot in self.slots.items()
            ],
        }
