class SafetyScanner:
    def __init__(self, node_id: str = "SCAN-1"):
        self.node_id = node_id
        # Position at entry conveyor start
        self.position = (0.5, 0.0, 1.0)
        # Sensors
        self.beam_broken: bool = False
        self.alarm_active: bool = False

    def to_dict(self) -> dict:
        return {
            "type": "scanner",
            "beam_broken": self.beam_broken,
            "alarm_active": self.alarm_active,
            "position": list(self.position),
        }
