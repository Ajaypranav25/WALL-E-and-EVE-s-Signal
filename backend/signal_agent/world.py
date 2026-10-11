"""World construction: turns a MissionConfig into a fully resolved, deterministic world.

Anything the config leaves out (map, EVE, clues, decoys, initial signal) is
generated from ``config.seed`` so the same config always yields the same world.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from . import physics
from .config import CLUE_KINDS, STATUSES, ClueKind, Coord, EveStatus, InitialSignal, MissionConfig

OPEN, WALL, RUBBLE, UNKNOWN = 0, 1, 2, 3
TERRAIN_SYMBOLS = {".": OPEN, "#": WALL, "~": RUBBLE}
STATUS_PRIOR = (0.5, 0.3, 0.2)
NEIGHBOURS = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass(frozen=True)
class Clue:
    id: str
    kind: ClueKind
    position: Coord
    misleading: bool


@dataclass(frozen=True)
class Decoy:
    id: str
    position: Coord
    power_dbm: float


@dataclass(frozen=True)
class World:
    grid: np.ndarray  # (height, width) terrain codes; never mutated after build
    start: Coord
    chargers: tuple[Coord, ...]
    eve_position: Coord
    eve_status: EveStatus
    clues: tuple[Clue, ...]
    decoys: tuple[Decoy, ...]
    initial_signal: InitialSignal

    @property
    def width(self) -> int:
        return int(self.grid.shape[1])

    @property
    def height(self) -> int:
        return int(self.grid.shape[0])

    def in_bounds(self, cell: Coord) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def passable(self, cell: Coord) -> bool:
        return self.in_bounds(cell) and self.grid[cell[1], cell[0]] != WALL


def reachable_cells(grid: np.ndarray, start: Coord) -> set[Coord]:
    height, width = grid.shape
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in NEIGHBOURS:
            nxt = (x + dx, y + dy)
            if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in seen and grid[nxt[1], nxt[0]] != WALL:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _generate_grid(cfg: MissionConfig, rng: np.random.Generator) -> np.ndarray:
    spec = cfg.map
    if spec.layout is not None:
        return np.array([[TERRAIN_SYMBOLS[ch] for ch in row] for row in spec.layout], dtype=np.int8)
    width, height = spec.width, spec.height
    grid = np.zeros((height, width), dtype=np.int8)
    # Wall segments read like collapsed buildings rather than salt-and-pepper noise.
    target_walls = int(spec.wall_density * width * height)
    while int((grid == WALL).sum()) < target_walls:
        length = int(rng.integers(2, 7))
        x, y = int(rng.integers(0, width)), int(rng.integers(0, height))
        dx, dy = ((1, 0), (0, 1))[int(rng.integers(0, 2))]
        for i in range(length):
            cx, cy = x + dx * i, y + dy * i
            if 0 <= cx < width and 0 <= cy < height:
                grid[cy, cx] = WALL
    # Rubble fields are blobs around random seeds.
    target_rubble = int(spec.rubble_density * width * height)
    while int((grid == RUBBLE).sum()) < target_rubble:
        cx, cy = int(rng.integers(0, width)), int(rng.integers(0, height))
        radius = float(rng.uniform(1.0, 2.6))
        ys, xs = np.ogrid[:height, :width]
        blob = ((xs - cx) ** 2 + (ys - cy) ** 2 <= radius**2) & (grid == OPEN)
        if not blob.any():
            continue
        grid[blob] = RUBBLE
    return grid


def _check_cell(name: str, cell: Coord, grid: np.ndarray) -> None:
    height, width = grid.shape
    if not (0 <= cell[0] < width and 0 <= cell[1] < height):
        raise ValueError(f"{name} {cell} is outside the {width}x{height} map")
    if grid[cell[1], cell[0]] == WALL:
        raise ValueError(f"{name} {cell} is inside a wall")


def _pick(rng: np.random.Generator, cells: list[Coord]) -> Coord:
    if not cells:
        raise ValueError("map has no free cell left for placement; lower wall density or enlarge the map")
    return cells[int(rng.integers(0, len(cells)))]


def build_world(cfg: MissionConfig) -> World:
    rng = np.random.default_rng(cfg.seed)
    grid = _generate_grid(cfg, rng)
    height, width = grid.shape

    start = cfg.start or (1, height - 2)
    if cfg.start is None:
        grid[start[1], start[0]] = OPEN
    _check_cell("start", start, grid)

    reach = reachable_cells(grid, start)
    if cfg.map.layout is None:
        # Seal pockets the rover could never reach so every open cell is meaningful.
        for y in range(height):
            for x in range(width):
                if grid[y, x] != WALL and (x, y) not in reach:
                    grid[y, x] = WALL
    free = sorted(reach)
    span = max(width, height)

    chargers = list(cfg.chargers) if cfg.chargers is not None else [start]
    if cfg.chargers is None:
        far = [c for c in free if physics.distance(c, start) >= span * 0.5]
        chargers.append(_pick(rng, far or free))
    for c in chargers:
        _check_cell("charger", c, grid)
        if c not in reach:
            raise ValueError(f"charger {c} is not reachable from start")

    if cfg.eve.position is not None:
        eve_pos = cfg.eve.position
        _check_cell("eve", eve_pos, grid)
    else:
        candidates = [c for c in free if physics.distance(c, start) >= span * 0.45 and c not in chargers]
        eve_pos = _pick(rng, candidates or [c for c in free if c != start])
    eve_status: EveStatus = cfg.eve.status or STATUSES[int(rng.choice(3, p=STATUS_PRIOR))]

    taken = {start, eve_pos, *chargers}
    clues = _resolve_clues(cfg, rng, grid, free, start, eve_pos, taken)
    taken |= {c.position for c in clues}
    decoys = _resolve_decoys(cfg, rng, grid, free, start, eve_pos, taken)
    initial = cfg.initial_signal or _generate_initial_signal(rng, start, eve_pos, eve_status, cfg.sensors.bearing_noise_deg)

    grid.setflags(write=False)
    return World(grid, start, tuple(chargers), eve_pos, eve_status, tuple(clues), tuple(decoys), initial)


def _resolve_clues(cfg, rng, grid, free, start, eve_pos, taken) -> list[Clue]:
    if cfg.clues is not None:
        out = []
        for i, spec in enumerate(cfg.clues):
            _check_cell("clue", spec.position, grid)
            out.append(Clue(f"clue-{i + 1}", spec.kind, spec.position, spec.misleading))
        return out
    trek = physics.distance(start, eve_pos)
    # Clues cluster along the corridor between base and EVE, where she passed.
    corridor = [
        c for c in free
        if c not in taken
        and 2.5 <= physics.distance(c, eve_pos) <= max(4.0, trek * 0.85)
        and physics.distance(c, start) + physics.distance(c, eve_pos) <= trek * 1.45 + 2
    ]
    pool = corridor or [c for c in free if c not in taken]
    out: list[Clue] = []
    for i in range(cfg.clue_count):
        pool = [c for c in pool if c not in taken]
        if not pool:
            break
        pos = _pick(rng, pool)
        taken = taken | {pos}
        kind = CLUE_KINDS[i % len(CLUE_KINDS)]
        out.append(Clue(f"clue-{i + 1}", kind, pos, bool(rng.random() < cfg.misleading_rate)))
    return out


def _resolve_decoys(cfg, rng, grid, free, start, eve_pos, taken) -> list[Decoy]:
    if cfg.decoys is not None:
        out = []
        for i, spec in enumerate(cfg.decoys):
            _check_cell("decoy", spec.position, grid)
            out.append(Decoy(f"decoy-{i + 1}", spec.position, spec.power_dbm))
        return out
    out = []
    for i in range(cfg.decoy_count):
        pool = [
            c for c in free
            if c not in taken and physics.distance(c, eve_pos) >= 8 and physics.distance(c, start) >= 6
        ]
        if not pool:
            break
        pos = _pick(rng, pool)
        taken = taken | {pos}
        out.append(Decoy(f"decoy-{i + 1}", pos, float(rng.uniform(-42.0, -36.0))))
    return out


def _generate_initial_signal(rng, start, eve_pos, status, noise_deg) -> InitialSignal:
    bearing = (physics.bearing_deg(start, eve_pos) + float(rng.normal(0, noise_deg))) % 360.0
    strength = float(physics.expected_strength(physics.EVE_POWER_DBM[status], physics.distance(start, eve_pos)))
    return InitialSignal(
        bearing_deg=round(bearing, 1) % 360.0,
        strength_dbm=round(strength + float(rng.normal(0, 2.0)), 1),
        timestamp=-int(rng.integers(5, 60)),
    )
