from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime


@dataclass
class Pallet:
    id: str
    position: tuple[float, float, float]  # (x, y, z) in meters
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    weight_kg: float = 100.0
    target_slot: str | None = None
    state: Literal['idle', 'moving', 'transferring', 'stored', 'error'] = 'idle'
    on_node: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
