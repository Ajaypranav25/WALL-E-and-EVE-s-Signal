"""Decision making. Every planner maps Memory -> Decision (one action plus its reasoning).

* ``ClassicalPlanner`` - belief-driven: picks the cell that buys the most
  probability of finding EVE per unit of battery, triangulates with periodic
  listens, detours for clues, and guards battery/time with a return-to-charger
  margin.
* ``GreedyPlanner`` - baseline: chases the loudest ping, keeps no belief.

Both share ``safety_check`` so comparisons isolate the search strategy.
"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np

from . import physics
from .environment import Action
from .memory import Coord, Decision, Memory
from .navigation import CostField, direction_to, disk_sum

SCAN_HERE_MASS = 0.22        # scan on the spot when this much probability is in range
RESCAN_COOLDOWN = 15         # ticks before re-scanning the same cell for the same reason
SWEEP_INTERVAL = 8           # ticks between opportunistic clue-sweep scans
LISTEN_MIN_GAP = 5           # ticks between listens ...
LISTEN_BASELINE = 4.0        # ... and cells moved, for a useful triangulation baseline
LISTEN_MAX_GAP = 18          # always re-listen after this long
CONCENTRATED_MASS = 0.7      # belief this peaked in one scan disk: stop listening, go look
GOAL_HYSTERESIS = 0.7        # keep the current goal unless a rival is clearly better
RETURN_COST_WEIGHT = 0.25    # prefer goals that leave WALL-E close to a charger
CLUE_DETOUR_LIMIT = 14.0     # max battery to spend walking to a detected clue


class Planner(Protocol):
    name: str

    def decide(self, mem: Memory) -> Decision: ...


# --------------------------------------------------------------------- safety
def _go_home(mem: Memory, mode: str, reason: str) -> Decision:
    path = mem.to_charger().path(mem.position)
    if not path:
        return Decision(Action("end"), mode, None, f"{reason} No known route to a charger, so WALL-E holds position and ends the mission.")
    return Decision(Action("move", direction_to(mem.position, path[0])), mode, path[-1], reason)


def safety_check(mem: Memory) -> Decision | None:
    """Battery and time guard rails. Returns a Decision when they must override the search."""
    cfg = mem.config
    costs, res = cfg.costs, cfg.resources
    pos = mem.position
    at_charger = pos in mem.chargers
    home = mem.home_cost()
    worst_action = max(costs.scan, costs.rubble_move, costs.listen)

    if not math.isfinite(home):
        return None  # fog of war hides every route; keep exploring rather than freeze
    steps_home = mem.home_steps() * costs.time_move
    if mem.time_left <= steps_home + costs.time_scan + 1:
        if at_charger:
            return Decision(Action("end"), "return", pos, f"Only {mem.time_left} ticks left; ending the mission safely at charger {pos}.")
        return _go_home(mem, "return", f"Only {mem.time_left} ticks left and the nearest charger is {steps_home} away; turning back.")

    if at_charger and mem.mode == "recharge" and mem.battery < res.battery_max - 1e-6:
        return Decision(Action("recharge"), "recharge", pos, f"Recharging at {pos}: {mem.battery:.0f}/{res.battery_max:.0f}.")

    if mem.battery < home + res.reserve + worst_action:
        if at_charger:
            return Decision(Action("recharge"), "recharge", pos, f"Battery {mem.battery:.1f} is below a safe margin; recharging at {pos}.")
        return _go_home(
            mem,
            "recharge",
            f"Battery {mem.battery:.1f} barely covers the {home:.1f} needed to reach a charger plus {res.reserve:.0f} reserve; heading to recharge.",
        )
    return None


# ------------------------------------------------------------------ targets
def target_utility(mem: Memory) -> tuple[np.ndarray, np.ndarray, CostField]:
    """Value of driving to each cell and scanning there.

    utility = belief mass within scan range / (battery to get there + scan +
    a fraction of the trip home). Cells WALL-E cannot reach, scan and still
    return from with its reserve intact get -inf.
    """
    cfg = mem.config
    mass = disk_sum(mem.belief.location, cfg.sensors.scan_radius)
    here = mem.from_here()
    home = mem.to_charger().cost
    total = here.cost + cfg.costs.scan + home + cfg.resources.reserve
    feasible = np.isfinite(total) & (total <= mem.battery)
    with np.errstate(invalid="ignore"):
        utility = np.where(feasible, mass / (here.cost + cfg.costs.scan + RETURN_COST_WEIGHT * home + 1.0), -np.inf)
    return utility, mass, here


def rank_targets(mem: Memory, k: int = 8) -> list[dict]:
    utility, mass, here = target_utility(mem)
    home = mem.to_charger().cost
    w = utility.shape[1]
    out = []
    for i in np.argsort(utility.ravel())[::-1][:k]:
        if not np.isfinite(utility.flat[i]):
            break
        out.append({
            "cell": [int(i % w), int(i // w)],
            "belief_in_scan_range": round(float(mass.flat[i]), 3),
            "battery_to_reach": round(float(here.cost.flat[i]), 1),
            "battery_home_from_there": round(float(home.flat[i]), 1),
            "utility": round(float(utility.flat[i]), 4),
        })
    return out


# ------------------------------------------------------------------ classical
class ClassicalPlanner:
    name = "classical"

    def decide(self, mem: Memory) -> Decision:
        guard = safety_check(mem)
        if guard:
            return guard
        for decide_step in (self._inspect_here, self._investigate_clue, self._maybe_listen):
            decision = decide_step(mem)
            if decision:
                return decision
        return self._search(mem)

    # ---- clue handling
    def _inspect_here(self, mem: Memory) -> Decision | None:
        for cid, cpos in mem.pending_clues.items():
            if cpos == mem.position:
                return Decision(Action("inspect"), "investigate", cpos, f"Standing on {cid}; inspecting it.")
        return None

    def _investigate_clue(self, mem: Memory) -> Decision | None:
        if not mem.pending_clues:
            return None
        here = mem.from_here()
        res, costs = mem.config.resources, mem.config.costs
        best: tuple[float, str, Coord] | None = None
        for cid, cpos in mem.pending_clues.items():
            cost = float(here.cost[cpos[1], cpos[0]])
            affordable = cost + costs.inspect + mem.home_cost(cpos) + res.reserve <= mem.battery
            if math.isfinite(cost) and cost <= CLUE_DETOUR_LIMIT and affordable and (best is None or cost < best[0]):
                best = (cost, cid, cpos)
        if best is None:
            return None
        cost, cid, cpos = best
        path = here.path(cpos)
        return Decision(
            Action("move", direction_to(mem.position, path[0])),
            "investigate",
            cpos,
            f"Scan revealed {cid} at {cpos}; detouring {cost:.1f} battery to read it before searching on.",
        )

    # ---- signal
    def _maybe_listen(self, mem: Memory) -> Decision | None:
        since = mem.tick - mem.last_listen_tick
        moved = physics.distance(mem.position, mem.last_listen_pos) if mem.last_listen_pos else math.inf
        r = mem.config.sensors.scan_radius
        peak = float(disk_sum(mem.belief.location, r).max())
        if peak >= CONCENTRATED_MASS and mem.last_listen_pos is not None:
            return None
        if mem.last_listen_pos is None:
            reason = "No live fix yet; listening for EVE's beacon before committing to a direction."
        elif since >= LISTEN_MIN_GAP and moved >= LISTEN_BASELINE:
            reason = f"Moved {moved:.1f} cells since the last fix; listening again to triangulate from a new baseline."
        elif since >= LISTEN_MAX_GAP:
            reason = f"{since} ticks since the last fix; refreshing the bearing."
        else:
            return None
        return Decision(Action("listen"), "listen", mem.goal, reason)

    # ---- search
    def _search(self, mem: Memory) -> Decision:
        costs = mem.config.costs
        pos = mem.position
        utility, mass, here = target_utility(mem)

        mass_here = float(mass[pos[1], pos[0]])
        recently_scanned = mem.tick - mem.scan_ticks.get(pos, -999) < RESCAN_COOLDOWN
        if mass_here >= SCAN_HERE_MASS and not recently_scanned:
            return Decision(Action("scan"), "search", pos, f"{mass_here:.0%} of the belief lies within scan range here; scanning.")

        if not np.isfinite(utility).any() or float(utility.max()) <= 0:
            return self._no_goal(mem)

        flat = np.argsort(utility.ravel())[::-1][:3]
        w = utility.shape[1]
        considered = tuple(
            {"cell": [int(i % w), int(i // w)], "utility": round(float(utility.flat[i]), 4), "mass": round(float(mass.flat[i]), 3), "cost": round(float(here.cost.flat[i]), 1)}
            for i in flat
            if np.isfinite(utility.flat[i])
        )
        best = (int(flat[0] % w), int(flat[0] // w))
        goal = best
        why = f"Best value target {best}: {mass[best[1], best[0]]:.0%} belief within scan range for {here.cost[best[1], best[0]]:.1f} battery."
        if mem.goal and mem.mode == "search" and mem.goal != pos:
            gx, gy = mem.goal
            if np.isfinite(utility[gy, gx]) and utility[gy, gx] >= GOAL_HYSTERESIS * utility[best[1], best[0]]:
                goal = mem.goal
                why = f"Holding course for {goal} ({mass[gy, gx]:.0%} belief in range); no rival is clearly better."

        if goal == pos:
            if not recently_scanned:
                return Decision(Action("scan"), "search", pos, f"Reached target {pos}; scanning.", considered)
            # Already scanned here: pick the best target elsewhere.
            utility[pos[1], pos[0]] = -np.inf
            idx = int(np.argmax(utility))
            if not np.isfinite(utility.flat[idx]):
                return self._no_goal(mem)
            goal = (idx % w, idx // w)
            why = f"Scanned {pos} already; moving on to {goal}."

        if mem.tick - mem.last_scan_tick >= SWEEP_INTERVAL and not recently_scanned:
            gap = "No scan yet" if mem.last_scan_pos is None else f"{mem.tick - mem.last_scan_tick} ticks since the last scan"
            return Decision(Action("scan"), "search", goal, f"{gap}; sweeping for clues on the way to {goal}.", considered)

        path = here.path(goal)
        return Decision(Action("move", direction_to(pos, path[0])), "search", goal, why, considered)

    def _no_goal(self, mem: Memory) -> Decision:
        res = mem.config.resources
        if mem.battery < res.battery_max * 0.9:
            if mem.position in mem.chargers:
                return Decision(Action("recharge"), "recharge", mem.position, "Nothing promising is reachable on the current charge; recharging first.")
            return _go_home(mem, "recharge", "Nothing promising is reachable on the current charge; heading to a charger to extend range.")
        if mem.position in mem.chargers:
            return Decision(Action("end"), "return", mem.position, "No reachable region holds meaningful probability; ending at base with an inconclusive report.")
        return _go_home(mem, "return", "No reachable region holds meaningful probability; returning to base.")


# --------------------------------------------------------------------- greedy
class GreedyPlanner:
    """Baseline: walk toward the loudest ping, scan every few steps, no belief model."""

    name = "greedy"
    LISTEN_EVERY = 4
    SCAN_EVERY = 3
    STRIDE = 6

    def __init__(self) -> None:
        self._heading: float | None = None

    def decide(self, mem: Memory) -> Decision:
        guard = safety_check(mem)
        if guard:
            return guard
        if self._heading is None:
            sig = mem.config.initial_signal
            if sig and sig.bearing_deg is not None:
                self._heading = sig.bearing_deg
            elif sig and sig.coordinates:
                self._heading = physics.bearing_deg(mem.position, sig.coordinates)
        if mem.tick - mem.last_listen_tick >= self.LISTEN_EVERY:
            return Decision(Action("listen"), "listen", None, "Greedy: periodic listen.", source=self.name)
        if mem.last_pings:
            loudest = max(mem.last_pings, key=lambda p: p["strength_dbm"])
            self._heading = loudest["bearing_deg"]
        if mem.tick - mem.last_scan_tick >= self.SCAN_EVERY:
            return Decision(Action("scan"), "search", None, "Greedy: periodic scan.", source=self.name)
        heading = self._heading if self._heading is not None else 0.0
        here = mem.from_here()
        target = self._project(mem, heading, here.cost)
        path = here.path(target)
        if not path:
            self._heading = (heading + 90.0) % 360.0
            return Decision(Action("scan"), "search", None, "Greedy: blocked, scanning and turning.", source=self.name)
        return Decision(Action("move", direction_to(mem.position, path[0])), "search", target, f"Greedy: chasing the loudest ping at {heading:.0f}°.", source=self.name)

    def _project(self, mem: Memory, heading: float, here: np.ndarray) -> Coord:
        rad = math.radians(heading)
        x = mem.position[0] + self.STRIDE * math.sin(rad)
        y = mem.position[1] - self.STRIDE * math.cos(rad)
        w, h = mem.known.width, mem.known.height
        tx, ty = int(round(min(max(x, 0), w - 1))), int(round(min(max(y, 0), h - 1)))
        # Snap to the nearest reachable cell around the projected point.
        ys, xs = np.mgrid[:h, :w]
        reachable = np.isfinite(here).copy()
        reachable[mem.position[1], mem.position[0]] = False
        score = np.where(reachable, (xs - tx) ** 2 + (ys - ty) ** 2, np.inf)
        idx = int(np.argmin(score))
        return (idx % w, idx // w)


PLANNERS = {"classical": ClassicalPlanner, "greedy": GreedyPlanner}
