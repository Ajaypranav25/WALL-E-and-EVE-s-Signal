"""What WALL-E knows: its own state, map, belief and evidence bookkeeping.

Built only from the mission brief and observations; it never touches the World.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .belief import Belief
from .config import MissionConfig
from .environment import Action
from .navigation import CostField, KnownMap, dijkstra

Coord = tuple[int, int]


@dataclass(frozen=True)
class Decision:
    action: Action
    mode: str
    goal: Coord | None
    reasoning: str
    considered: tuple[dict[str, Any], ...] = ()
    source: str = "classical"


@dataclass
class Memory:
    config: MissionConfig
    position: Coord
    battery: float
    known: KnownMap
    belief: Belief
    chargers: tuple[Coord, ...]
    start: Coord
    tick: int = 0
    time_used: int = 0
    mode: str = "start"
    goal: Coord | None = None
    pending_clues: dict[str, Coord] = field(default_factory=dict)
    inspected: dict[str, dict[str, Any]] = field(default_factory=dict)
    decoys: dict[str, Coord] = field(default_factory=dict)
    eve_found: dict[str, Any] | None = None
    last_scan_tick: int = -999
    last_scan_pos: Coord | None = None
    scan_ticks: dict[Coord, int] = field(default_factory=dict)
    last_listen_tick: int = -999
    last_listen_pos: Coord | None = None
    suspicious_pings: int = 0
    last_pings: tuple[dict[str, float], ...] = ()
    _home_cache: tuple[int, CostField] | None = field(default=None, repr=False)

    # ----------------------------------------------------------- navigation
    def from_here(self) -> CostField:
        return dijkstra(self.known.entry_costs(self.config.costs), [self.position])

    def to_charger(self) -> CostField:
        """Reverse cost field to the nearest charger; cached until the map changes."""
        if self._home_cache is None or self._home_cache[0] != self.known.version:
            field_ = dijkstra(self.known.entry_costs(self.config.costs), list(self.chargers), reverse=True)
            self._home_cache = (self.known.version, field_)
        return self._home_cache[1]

    def home_cost(self, cell: Coord | None = None) -> float:
        c = cell or self.position
        return float(self.to_charger().cost[c[1], c[0]])

    def home_steps(self) -> int:
        return len(self.to_charger().path(self.position))

    @property
    def time_left(self) -> int:
        return self.config.resources.time_limit - self.time_used

    def summary(self) -> dict[str, Any]:
        (mx, my), p = self.belief.map_estimate()
        return {
            "position": list(self.position),
            "battery": round(self.battery, 2),
            "time_used": self.time_used,
            "time_left": self.time_left,
            "mode": self.mode,
            "goal": list(self.goal) if self.goal else None,
            "map_estimate": [mx, my],
            "map_p": round(p, 4),
            "entropy_bits": round(self.belief.entropy_bits(), 3),
            "status": {k: round(v, 3) for k, v in self.belief.status.items()},
            "pending_clues": len(self.pending_clues),
            "decoys_known": len(self.decoys),
        }
