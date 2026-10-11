"""Simulated wasteland. Loads a world, applies actions, returns noisy observations.

The environment is the only component that knows where EVE, the clues and
the decoys really are. Everything it reveals goes through an Observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from . import physics
from .config import STATUSES, MissionConfig
from .world import RUBBLE, World, build_world

ActionKind = Literal["move", "scan", "listen", "inspect", "recharge", "end"]
Direction = Literal["N", "E", "S", "W"]
DIRECTIONS: dict[str, tuple[int, int]] = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    direction: Direction | None = None

    def __post_init__(self) -> None:
        if self.kind == "move" and self.direction not in DIRECTIONS:
            raise ValueError("move needs a direction of N, E, S or W")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "direction": self.direction} if self.direction else {"kind": self.kind}


@dataclass(frozen=True)
class Observation:
    tick: int
    position: tuple[int, int]
    battery: float
    time_used: int
    result: str
    terrain: tuple[tuple[int, int, int], ...] = ()
    detections: tuple[dict[str, Any], ...] = ()
    pings: tuple[dict[str, float], ...] = ()
    clue: dict[str, Any] | None = None
    at_charger: bool = False
    done: bool = False
    outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tick": self.tick,
            "position": list(self.position),
            "battery": round(self.battery, 2),
            "time_used": self.time_used,
            "result": self.result,
            "at_charger": self.at_charger,
        }
        if self.detections:
            out["detections"] = list(self.detections)
        if self.pings:
            out["pings"] = list(self.pings)
        if self.clue:
            out["clue"] = self.clue
        if self.done:
            out["done"] = True
            out["outcome"] = self.outcome
        return out


@dataclass
class _State:
    position: tuple[int, int]
    battery: float
    time_used: int = 0
    tick: int = 0
    done: bool = False
    outcome: str | None = None
    eve_seen: bool = False
    inspected: set[str] = field(default_factory=set)


class Environment:
    """Step-based simulator. ``step`` is the only way to change or learn about the world."""

    def __init__(self, config: MissionConfig, world: World | None = None, noise_seed: int | None = None):
        self.config = config
        self.world = world or build_world(config)
        self._rng = np.random.default_rng(config.seed + 7919 if noise_seed is None else noise_seed)
        self._state = _State(position=self.world.start, battery=config.resources.start)

    # ---------------------------------------------------------------- public
    @property
    def done(self) -> bool:
        return self._state.done

    @property
    def outcome(self) -> str | None:
        return self._state.outcome

    def reset_observation(self) -> Observation:
        return self._observe("mission start")

    def step(self, action: Action) -> Observation:
        if self._state.done:
            raise RuntimeError("mission is over; no further actions allowed")
        handler = {
            "move": self._move,
            "scan": self._scan,
            "listen": self._listen,
            "inspect": self._inspect,
            "recharge": self._recharge,
            "end": self._end,
        }[action.kind]
        self._state.tick += 1
        obs = handler(action)
        if not self._state.done and self._state.time_used >= self.config.resources.time_limit:
            self._finish("time_exhausted")
            obs = self._with_done(obs)
        return obs

    # --------------------------------------------------------------- helpers
    def _spend(self, battery: float, time: int) -> bool:
        """Charge an action's cost. Returns False (and strands WALL-E) if the battery runs dry."""
        s = self._state
        s.time_used += time
        if battery > s.battery + 1e-9:
            s.battery = 0.0
            self._finish("stranded")
            return False
        s.battery -= battery
        return True

    def _finish(self, outcome: str) -> None:
        self._state.done = True
        self._state.outcome = outcome

    def _with_done(self, obs: Observation) -> Observation:
        return Observation(**{**obs.__dict__, "done": True, "outcome": self._state.outcome, "battery": self._state.battery, "time_used": self._state.time_used})

    def _terrain_patch(self) -> tuple[tuple[int, int, int], ...]:
        radius = self.config.sensors.view_radius
        px, py = self._state.position
        cells = []
        for y in range(py - radius, py + radius + 1):
            for x in range(px - radius, px + radius + 1):
                if self.world.in_bounds((x, y)):
                    cells.append((x, y, int(self.world.grid[y, x])))
        return tuple(cells)

    def _observe(self, result: str, **extra: Any) -> Observation:
        s = self._state
        return Observation(
            tick=s.tick,
            position=s.position,
            battery=s.battery,
            time_used=s.time_used,
            result=result,
            terrain=self._terrain_patch(),
            at_charger=s.position in self.world.chargers,
            done=s.done,
            outcome=s.outcome,
            **extra,
        )

    # --------------------------------------------------------------- actions
    def _move(self, action: Action) -> Observation:
        dx, dy = DIRECTIONS[action.direction]  # type: ignore[index]
        x, y = self._state.position
        target = (x + dx, y + dy)
        costs = self.config.costs
        if not self.world.passable(target):
            # Bumping costs a little time and a sliver of battery, but WALL-E stays put.
            self._spend(costs.move * 0.25, 1)
            return self._observe("blocked")
        rubble = self.world.grid[target[1], target[0]] == RUBBLE
        if self._spend(costs.rubble_move if rubble else costs.move, costs.time_move):
            self._state.position = target
        return self._observe("moved" if not self._state.done else "battery depleted")

    def _scan(self, _: Action) -> Observation:
        costs, sensors = self.config.costs, self.config.sensors
        if not self._spend(costs.scan, costs.time_scan):
            return self._observe("battery depleted")
        pos = self._state.position
        found: list[dict[str, Any]] = []
        if physics.distance(pos, self.world.eve_position) <= sensors.scan_radius and self._rng.random() < sensors.eve_detect_prob:
            found.append({"type": "eve", "position": list(self.world.eve_position), "status": self._read_status()})
            self._state.eve_seen = True
        for clue in self.world.clues:
            if physics.distance(pos, clue.position) <= sensors.scan_radius and self._rng.random() < sensors.clue_detect_prob:
                found.append({"type": "clue", "id": clue.id, "position": list(clue.position)})
        for decoy in self.world.decoys:
            if physics.distance(pos, decoy.position) <= sensors.scan_radius and self._rng.random() < sensors.eve_detect_prob:
                found.append({"type": "decoy", "id": decoy.id, "position": list(decoy.position)})
        if self._state.eve_seen:
            self._finish("eve_located")
        return self._observe(f"scan found {len(found)} object(s)", detections=tuple(found))

    def _read_status(self) -> str:
        accuracy = self.config.sensors.status_read_accuracy
        truth = self.world.eve_status
        if self._rng.random() < accuracy:
            return truth
        others = [s for s in STATUSES if s != truth]
        return others[int(self._rng.integers(0, len(others)))]

    def _listen(self, _: Action) -> Observation:
        costs, sensors = self.config.costs, self.config.sensors
        if not self._spend(costs.listen, costs.time_listen):
            return self._observe("battery depleted")
        pos = self._state.position
        sources = [(self.world.eve_position, physics.EVE_POWER_DBM[self.world.eve_status], physics.EVE_EMIT_PROB[self.world.eve_status])]
        sources += [(d.position, d.power_dbm, physics.DECOY_EMIT_PROB) for d in self.world.decoys]
        pings = []
        for src, power, emit_prob in sources:
            if self._rng.random() >= emit_prob:
                continue
            dist = physics.distance(pos, src)
            strength = float(physics.expected_strength(power, dist)) + float(self._rng.normal(0, sensors.strength_noise_db))
            if strength < sensors.sensitivity_dbm:
                continue
            true_bearing = physics.bearing_deg(pos, src) if dist > 0 else float(self._rng.uniform(0, 360))
            bearing = (true_bearing + float(self._rng.normal(0, sensors.bearing_noise_deg))) % 360.0
            pings.append({"bearing_deg": round(bearing, 1), "strength_dbm": round(strength, 1)})
        # The receiver cannot tell sources apart, so present pings in random order.
        order = self._rng.permutation(len(pings))
        return self._observe(f"heard {len(pings)} ping(s)", pings=tuple(pings[i] for i in order))

    def _inspect(self, _: Action) -> Observation:
        if not self._spend(self.config.costs.inspect, self.config.costs.time_inspect):
            return self._observe("battery depleted")
        here = [c for c in self.world.clues if c.position == self._state.position]
        clue = next((c for c in here if c.id not in self._state.inspected), here[0] if here else None)
        if clue is None:
            return self._observe("nothing to inspect here")
        self._state.inspected.add(clue.id)
        return self._observe(f"inspected {clue.kind}", clue=self._clue_content(clue))

    def _recharge(self, _: Action) -> Observation:
        costs, res = self.config.costs, self.config.resources
        self._state.time_used += costs.time_recharge
        if self._state.position not in self.world.chargers:
            return self._observe("no charger here")
        self._state.battery = min(res.battery_max, self._state.battery + costs.recharge_rate)
        return self._observe("recharged")

    def _end(self, _: Action) -> Observation:
        self._finish("returned_to_base" if self._state.position in self.world.chargers else "aborted_in_field")
        return self._observe("mission ended by agent")

    # ---------------------------------------------------------- clue content
    def _clue_content(self, clue) -> dict[str, Any]:
        """Turn a clue into what WALL-E reads off it. Misleading clues point somewhere random."""
        rng = self._rng
        eve, status = self.world.eve_position, self.world.eve_status
        if clue.misleading:
            eve = (int(rng.integers(0, self.world.width)), int(rng.integers(0, self.world.height)))
            status = STATUSES[int(rng.integers(0, 3))]
        base = {"id": clue.id, "kind": clue.kind, "position": list(clue.position)}
        if clue.kind == "tracks":
            bearing = (physics.bearing_deg(clue.position, eve) + float(rng.normal(0, 15.0))) % 360.0
            return {**base, "bearing_deg": round(bearing, 1), "message": f"Hover-tracks scored into the dust, heading {bearing:.0f}°."}
        if clue.kind == "log_fragment":
            sector = COMPASS[int(((physics.bearing_deg(clue.position, eve) + 22.5) % 360) // 45)]
            return {**base, "sector": sector, "message": f"A charred log fragment: 'EVE last vectored {sector}.'"}
        if clue.kind == "scorch_mark":
            dist = physics.distance(clue.position, eve)
            estimate = max(0.0, dist * (1 + float(rng.normal(0, 0.15))))
            return {**base, "distance_estimate": round(estimate, 1), "message": f"Fresh blaster scorch. Plasma residue suggests the source is ~{estimate:.0f} cells away."}
        hints = {"active": "a fresh seedling in a boot", "dormant": "a wilted seedling, untouched for days", "damaged": "a crushed boot and torn plating"}
        shown = status if rng.random() < 0.8 else STATUSES[int(rng.integers(0, 3))]
        return {**base, "status_hint": shown, "message": f"Found {hints[shown]}."}
