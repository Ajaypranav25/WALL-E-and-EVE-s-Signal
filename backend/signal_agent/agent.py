"""The autonomous agent loop: observe -> update belief -> decide -> act -> log."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import physics
from .belief import Belief, Evidence, initial_passable
from .config import MissionConfig
from .environment import Action, Environment, Observation
from .memory import Decision, Memory
from .navigation import KnownMap
from .planner import PLANNERS, Planner
from .trace import TraceRecorder

SUSPICIOUS_PING_SCORE = 0.9
GOAL_SHIFT_CELLS = 4.0


def make_memory(config: MissionConfig, env: Environment) -> Memory:
    """Build WALL-E's starting knowledge from the brief only (map if surveyed, chargers, start)."""
    world = env.world
    known = KnownMap.from_world_grid(world.grid, config.map.known)
    belief = Belief(world.width, world.height, config.sensors, initial_passable(world.grid, config.map.known))
    mem = Memory(config, world.start, config.resources.start, known, belief, world.chargers, world.start)
    belief.add(Evidence("initial", world.start, {"signal": world.initial_signal}, 0))
    return mem


@dataclass
class Agent:
    config: MissionConfig
    env: Environment
    planner: Planner
    recorder: TraceRecorder = field(default_factory=TraceRecorder)

    def __post_init__(self) -> None:
        self.mem = make_memory(self.config, self.env)

    @classmethod
    def create(cls, config: MissionConfig, planner: str | Planner = "classical", **planner_kwargs: Any) -> Agent:
        env = Environment(config)
        if isinstance(planner, str):
            if planner == "llm":
                from .llm_planner import LLMPlanner

                planner_obj: Planner = LLMPlanner(**planner_kwargs)
            elif planner in PLANNERS:
                planner_obj = PLANNERS[planner]()
            else:
                raise ValueError(f"unknown planner {planner!r}; choose from {sorted([*PLANNERS, 'llm'])}")
        else:
            planner_obj = planner
        return cls(config, env, planner_obj)

    # ------------------------------------------------------------------ loop
    def run(self, max_steps: int | None = None) -> str:
        limit = max_steps or self.config.resources.time_limit * 2
        first = self.env.reset_observation()
        notes = self._absorb(first)
        self.recorder.start(self.mem, first, notes)
        steps = 0
        while not self.env.done and steps < limit:
            decision = self.planner.decide(self.mem)
            change = self._strategy_change(decision)
            obs = self.env.step(decision.action)
            self.mem.mode, self.mem.goal = decision.mode, decision.goal
            notes = self._absorb(obs, decision)
            self.recorder.step(self.mem, decision, obs, notes, change)
            steps += 1
        if not self.env.done:
            self.env.step(Action("end"))
        return self.env.outcome or "unknown"

    def _strategy_change(self, d: Decision) -> dict[str, Any] | None:
        prev_mode, prev_goal = self.mem.mode, self.mem.goal
        # Listening and inspecting are brief interludes, not strategy shifts.
        if d.mode in {"listen"} or (d.mode == prev_mode and _same_goal(prev_goal, d.goal)):
            return None
        if d.mode == prev_mode == "search" and prev_goal and d.goal and physics.distance(prev_goal, d.goal) < GOAL_SHIFT_CELLS:
            return None
        if prev_mode == "listen" and d.mode == "search" and self.recorder.last_search_goal and d.goal and physics.distance(self.recorder.last_search_goal, d.goal) < GOAL_SHIFT_CELLS:
            return None
        return {"from": prev_mode, "to": d.mode, "goal": list(d.goal) if d.goal else None, "reason": d.reasoning}

    # -------------------------------------------------------------- learning
    def _absorb(self, obs: Observation, decision: Decision | None = None) -> list[str]:
        """Fold an observation into memory and belief. Returns human-readable notes for the trace."""
        mem = self.mem
        notes: list[str] = []
        mem.tick, mem.position, mem.battery, mem.time_used = obs.tick, obs.position, obs.battery, obs.time_used
        for wall in mem.known.update(obs.terrain):
            mem.belief.mark_wall(wall)
        if obs.result == "blocked":
            notes.append("Bumped into unseen debris; map updated and route re-planned.")
        kind = decision.action.kind if decision else None
        if kind == "listen":
            notes += self._absorb_pings(obs)
        elif kind == "scan":
            notes += self._absorb_scan(obs)
        elif kind == "inspect" and obs.clue:
            notes += self._absorb_clue(obs)
        return notes

    def _absorb_pings(self, obs: Observation) -> list[str]:
        mem = self.mem
        pings = list(obs.pings)
        notes = []
        for p in pings:
            score = mem.belief.ping_outlier_score(obs.position, p)
            if score >= SUSPICIOUS_PING_SCORE:
                mem.suspicious_pings += 1
                notes.append(f"Ping at {p['bearing_deg']:.0f}°/{p['strength_dbm']:.0f} dBm fits the belief poorly (outlier score {score:.2f}); possible spoofed or reflected signal, down-weighted.")
        mem.belief.add(Evidence("pings", obs.position, {"pings": pings}, obs.tick))
        mem.last_listen_tick, mem.last_listen_pos, mem.last_pings = obs.tick, obs.position, tuple(pings)
        if not pings:
            notes.append("Silence: no ping cleared the receiver threshold, which itself suggests EVE is far, dormant or damaged.")
        return notes

    def _absorb_scan(self, obs: Observation) -> list[str]:
        mem = self.mem
        notes = []
        mem.last_scan_tick, mem.last_scan_pos = obs.tick, obs.position
        mem.scan_ticks[obs.position] = obs.tick
        eve = next((d for d in obs.detections if d["type"] == "eve"), None)
        if eve:
            mem.eve_found = eve
            mem.belief.add(Evidence("eve_seen", obs.position, {"position": tuple(eve["position"]), "status": eve["status"]}, obs.tick))
            notes.append(f"EVE sighted at {tuple(eve['position'])}, reading as {eve['status']}.")
        else:
            mem.belief.add(Evidence("scan_miss", obs.position, {}, obs.tick))
        for d in obs.detections:
            pos = tuple(d["position"])
            if d["type"] == "clue" and d["id"] not in mem.inspected and d["id"] not in mem.pending_clues:
                mem.pending_clues[d["id"]] = pos
                notes.append(f"Detected {d['id']} at {pos}.")
            elif d["type"] == "decoy" and d["id"] not in mem.decoys:
                mem.decoys[d["id"]] = pos
                before = mem.belief.map_estimate()[0]
                mem.belief.add_decoy(d["id"], pos)
                after = mem.belief.map_estimate()[0]
                n = sum(1 for e in mem.belief.evidence if e.kind == "pings")
                notes.append(f"Found a spoofing transmitter ({d['id']}) at {pos}; re-read {n} past listens with it as a known decoy. Best estimate moved {before} -> {after}.")
        return notes

    def _absorb_clue(self, obs: Observation) -> list[str]:
        mem = self.mem
        clue = obs.clue or {}
        mem.pending_clues.pop(clue["id"], None)
        mem.inspected[clue["id"]] = clue
        payload = {k: v for k, v in clue.items() if k in {"bearing_deg", "sector", "distance_estimate", "status_hint"}}
        mem.belief.add(Evidence("clue", tuple(clue["position"]), payload, obs.tick))
        return [f"Read {clue['id']} ({clue['kind']}): {clue['message']}"]


def _same_goal(a, b) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and tuple(a) == tuple(b))
