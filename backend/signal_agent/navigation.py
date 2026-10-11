"""WALL-E's own map of the terrain plus Dijkstra path planning over battery cost."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from .config import Costs
from .world import NEIGHBOURS, OPEN, RUBBLE, UNKNOWN, WALL

# Planning assumes unexplored ground is a little worse than open ground.
UNKNOWN_COST_FACTOR = 1.3
INF = float("inf")


@dataclass
class KnownMap:
    grid: np.ndarray  # (h, w) terrain codes incl. UNKNOWN; owned and updated by the agent
    version: int = 0
    _cost_cache: tuple[int, np.ndarray] | None = field(default=None, repr=False)

    @classmethod
    def from_world_grid(cls, grid: np.ndarray, known: bool) -> KnownMap:
        return cls(grid.copy() if known else np.full(grid.shape, UNKNOWN, dtype=np.int8))

    @property
    def width(self) -> int:
        return int(self.grid.shape[1])

    @property
    def height(self) -> int:
        return int(self.grid.shape[0])

    def update(self, patch: tuple[tuple[int, int, int], ...] | list) -> list[tuple[int, int]]:
        """Merge an observed terrain patch. Returns newly discovered wall cells."""
        new_walls = []
        changed = False
        for x, y, code in patch:
            if self.grid[y, x] != code:
                if code == WALL:
                    new_walls.append((x, y))
                self.grid[y, x] = code
                changed = True
        if changed:
            self.version += 1
        return new_walls

    def entry_costs(self, costs: Costs) -> np.ndarray:
        if self._cost_cache is not None and self._cost_cache[0] == self.version:
            return self._cost_cache[1]
        table = np.full(self.grid.shape, INF)
        table[self.grid == OPEN] = costs.move
        table[self.grid == RUBBLE] = costs.rubble_move
        table[self.grid == UNKNOWN] = costs.move * UNKNOWN_COST_FACTOR
        self._cost_cache = (self.version, table)
        return table


@dataclass(frozen=True)
class CostField:
    """Result of a Dijkstra sweep: cost to every cell and how to get there."""

    cost: np.ndarray
    parent: np.ndarray  # (h, w) flat index of predecessor, -1 at sources/unreached
    reverse: bool

    def path(self, target: tuple[int, int]) -> list[tuple[int, int]]:
        """Cells from (exclusive) the source to target, or reversed for a reverse field."""
        w = self.cost.shape[1]
        if not np.isfinite(self.cost[target[1], target[0]]):
            return []
        cells = []
        idx = target[1] * w + target[0]
        while idx != -1:
            cells.append((idx % w, idx // w))
            idx = int(self.parent.flat[idx])
        if self.reverse:
            # Walk from target toward the source set; drop the starting cell itself.
            return cells[1:]
        cells.reverse()
        return cells[1:]


def dijkstra(entry_cost: np.ndarray, sources: list[tuple[int, int]], reverse: bool = False) -> CostField:
    """Forward: cost of travelling *from* the sources. Reverse: cost of travelling *to* them.

    Moving onto a cell costs that cell's entry cost.
    """
    h, w = entry_cost.shape
    cost = np.full((h, w), INF)
    parent = np.full((h, w), -1, dtype=np.int64)
    heap: list[tuple[float, int, int]] = []
    for sx, sy in sources:
        if np.isfinite(entry_cost[sy, sx]) or reverse:
            cost[sy, sx] = 0.0
            heap.append((0.0, sx, sy))
    heapq.heapify(heap)
    while heap:
        c, x, y = heapq.heappop(heap)
        if c > cost[y, x]:
            continue
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if not np.isfinite(entry_cost[ny, nx]):
                continue
            # Forward pays to enter the neighbour; reverse pays to enter the current cell.
            step = entry_cost[y, x] if reverse else entry_cost[ny, nx]
            if not np.isfinite(step):
                continue
            nc = c + step
            if nc < cost[ny, nx]:
                cost[ny, nx] = nc
                parent[ny, nx] = y * w + x
                heapq.heappush(heap, (nc, nx, ny))
    return CostField(cost, parent, reverse)


def disk_sum(field_: np.ndarray, radius: int) -> np.ndarray:
    """Sum of ``field_`` within Euclidean ``radius`` of every cell."""
    h, w = field_.shape
    padded = np.pad(field_, radius)
    out = np.zeros_like(field_, dtype=float)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                out += padded[radius + dy : radius + dy + h, radius + dx : radius + dx + w]
    return out


def direction_to(frm: tuple[int, int], to: tuple[int, int]) -> str:
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    return {(0, -1): "N", (1, 0): "E", (0, 1): "S", (-1, 0): "W"}[(dx, dy)]
