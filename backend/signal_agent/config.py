"""Mission configuration: schema, loading (JSON/YAML) and validation.

A config describes the *world* (map, EVE, clues, decoys) and the *brief* the
agent receives (initial signal, resource budget, action costs, sensor specs).
The agent only ever sees the brief; the world is private to the environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Coord = tuple[int, int]
EveStatus = Literal["active", "dormant", "damaged"]
ClueKind = Literal["tracks", "log_fragment", "scorch_mark", "plant"]

STATUSES: tuple[EveStatus, ...] = ("active", "dormant", "damaged")
CLUE_KINDS: tuple[ClueKind, ...] = ("tracks", "log_fragment", "scorch_mark", "plant")
MAX_GRID = 64


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MapSpec(_Strict):
    """Either an explicit ASCII ``layout`` or a procedurally generated grid."""

    width: int = Field(24, ge=8, le=MAX_GRID)
    height: int = Field(18, ge=8, le=MAX_GRID)
    wall_density: float = Field(0.12, ge=0.0, le=0.4)
    rubble_density: float = Field(0.15, ge=0.0, le=0.5)
    # Rows of '.', '#' (wall), '~' (rubble). Overrides width/height when given.
    layout: list[str] | None = None
    # When false the agent starts with fog of war and maps terrain as it goes.
    known: bool = True

    @field_validator("layout")
    @classmethod
    def _check_layout(cls, rows: list[str] | None) -> list[str] | None:
        if rows is None:
            return None
        if not 8 <= len(rows) <= MAX_GRID:
            raise ValueError(f"layout must have 8..{MAX_GRID} rows")
        width = len(rows[0])
        if not 8 <= width <= MAX_GRID or any(len(r) != width for r in rows):
            raise ValueError(f"layout rows must share one width in 8..{MAX_GRID}")
        bad = {ch for r in rows for ch in r} - set(".#~")
        if bad:
            raise ValueError(f"layout has unknown symbols: {sorted(bad)}")
        return rows


class InitialSignal(_Strict):
    """The last reading received before the mission starts.

    Give either a bearing (degrees clockwise from north, measured from the
    start cell) or approximate coordinates with an uncertainty radius.
    ``timestamp`` is the reading time in ticks relative to mission start
    (negative = older); stale readings are trusted less.
    """

    bearing_deg: float | None = Field(None, ge=0.0, lt=360.0)
    coordinates: Coord | None = None
    uncertainty: float = Field(4.0, gt=0.0, le=40.0)
    strength_dbm: float | None = Field(None, ge=-120.0, le=0.0)
    timestamp: int = Field(0, le=0, ge=-10_000)

    @model_validator(mode="after")
    def _one_of(self) -> InitialSignal:
        if self.bearing_deg is None and self.coordinates is None:
            raise ValueError("initial_signal needs bearing_deg or coordinates")
        return self


class Resources(_Strict):
    battery_max: float = Field(100.0, gt=0, le=10_000)
    battery_start: float | None = Field(None, gt=0)
    time_limit: int = Field(400, gt=0, le=20_000)
    reserve: float = Field(6.0, ge=0)

    @model_validator(mode="after")
    def _start_le_max(self) -> Resources:
        if self.battery_start is not None and self.battery_start > self.battery_max:
            raise ValueError("battery_start cannot exceed battery_max")
        return self

    @property
    def start(self) -> float:
        return self.battery_max if self.battery_start is None else self.battery_start


class Costs(_Strict):
    """Battery and time cost of each action."""

    move: float = Field(1.0, ge=0)
    rubble_move: float = Field(2.5, ge=0)
    scan: float = Field(2.0, ge=0)
    listen: float = Field(1.0, ge=0)
    inspect: float = Field(0.5, ge=0)
    recharge_rate: float = Field(15.0, gt=0)
    time_move: int = Field(1, ge=1)
    time_scan: int = Field(2, ge=1)
    time_listen: int = Field(1, ge=1)
    time_inspect: int = Field(1, ge=1)
    time_recharge: int = Field(1, ge=1)


class Sensors(_Strict):
    scan_radius: int = Field(2, ge=1, le=6)
    eve_detect_prob: float = Field(0.9, gt=0, le=1)
    clue_detect_prob: float = Field(0.85, gt=0, le=1)
    status_read_accuracy: float = Field(0.9, ge=0.34, le=1)
    bearing_noise_deg: float = Field(12.0, gt=0, le=90)
    strength_noise_db: float = Field(3.0, gt=0, le=20)
    sensitivity_dbm: float = Field(-92.0, le=0)
    view_radius: int = Field(2, ge=1, le=6)


class EveSpec(_Strict):
    position: Coord | None = None
    status: EveStatus | None = None


class ClueSpec(_Strict):
    kind: ClueKind
    position: Coord
    misleading: bool = False


class DecoySpec(_Strict):
    position: Coord
    power_dbm: float = Field(-38.0, ge=-80, le=0)


class MissionConfig(_Strict):
    name: str = Field("mission", min_length=1, max_length=80)
    description: str = Field("", max_length=2000)
    seed: int = Field(0, ge=0, le=2**31 - 1)
    map: MapSpec = MapSpec()
    start: Coord | None = None
    chargers: list[Coord] | None = Field(None, min_length=1, max_length=10)
    eve: EveSpec = EveSpec()
    initial_signal: InitialSignal | None = None
    resources: Resources = Resources()
    costs: Costs = Costs()
    sensors: Sensors = Sensors()
    clues: list[ClueSpec] | None = Field(None, max_length=40)
    clue_count: int = Field(5, ge=0, le=40)
    misleading_rate: float = Field(0.1, ge=0, le=0.5)
    decoys: list[DecoySpec] | None = Field(None, max_length=6)
    decoy_count: int = Field(0, ge=0, le=6)


    @model_validator(mode="after")
    def _distinct_clue_cells(self) -> MissionConfig:
        cells = [c.position for c in self.clues or []]
        if len(cells) != len(set(cells)):
            raise ValueError("two clues cannot share a cell")
        return self


def load_config(path: str | Path) -> MissionConfig:
    """Load and validate a mission config from a ``.json``, ``.yaml`` or ``.yml`` file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path.name}: {exc}") from exc
    elif suffix in {".yaml", ".yml"}:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML in {path.name}: {exc}") from exc
    else:
        raise ValueError(f"unsupported config type {suffix!r}; use .json, .yaml or .yml")
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return MissionConfig.model_validate(data)
