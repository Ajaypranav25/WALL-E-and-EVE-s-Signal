"""Run a mission end to end and package trace + report + world for output and the UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import Agent
from .config import MissionConfig
from .planner import Planner
from .report import build_report, render_markdown
from .world import RUBBLE, WALL, World

SYMBOL = {0: ".", WALL: "#", RUBBLE: "~"}


@dataclass(frozen=True)
class MissionResult:
    outcome: str
    report: dict[str, Any]
    steps: list[dict[str, Any]]
    world: dict[str, Any]
    agent: Agent

    def bundle(self) -> dict[str, Any]:
        """Single JSON document the visualizer loads."""
        return {"version": 1, "world": self.world, "report": self.report, "steps": self.steps}


def world_to_dict(world: World, config: MissionConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "description": config.description,
        "width": world.width,
        "height": world.height,
        "grid": ["".join(SYMBOL[int(v)] for v in row) for row in world.grid],
        "map_known": config.map.known,
        "start": list(world.start),
        "chargers": [list(c) for c in world.chargers],
        "eve": {"position": list(world.eve_position), "status": world.eve_status},
        "clues": [{"id": c.id, "kind": c.kind, "position": list(c.position), "misleading": c.misleading} for c in world.clues],
        "decoys": [{"id": d.id, "position": list(d.position), "power_dbm": round(d.power_dbm, 1)} for d in world.decoys],
        "initial_signal": world.initial_signal.model_dump(),
        "scan_radius": config.sensors.scan_radius,
        "battery_max": config.resources.battery_max,
        "time_limit": config.resources.time_limit,
    }


def _resource_stats(steps: list[dict[str, Any]], start_battery: float) -> tuple[float, int, int]:
    used, distance, recharges = 0.0, 0, 0
    prev = start_battery
    for rec in steps[1:]:
        battery = rec["observation"]["battery"]
        if battery < prev:
            used += prev - battery
        prev = battery
        if rec["observation"]["result"] == "moved":
            distance += 1
        if rec["observation"]["result"] == "recharged":
            recharges += 1
    return used, distance, recharges


def run_mission(config: MissionConfig, planner: str | Planner = "classical", max_steps: int | None = None, **planner_kwargs: Any) -> MissionResult:
    agent = Agent.create(config, planner, **planner_kwargs)
    outcome = agent.run(max_steps)
    steps = agent.recorder.records
    used, distance, recharges = _resource_stats(steps, config.resources.start)
    name = planner if isinstance(planner, str) else planner.name
    report = build_report(agent.mem, agent.env.world, outcome, name, agent.recorder, used, distance, recharges)
    return MissionResult(outcome, report, steps, world_to_dict(agent.env.world, config), agent)


def write_outputs(result: MissionResult, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "trace": out / "trace.jsonl",
        "report_json": out / "report.json",
        "report_md": out / "report.md",
        "bundle": out / "run.json",
        "ascii": out / "map.txt",
    }
    result.agent.recorder.write_jsonl(paths["trace"])
    paths["report_json"].write_text(json.dumps(result.report, indent=2), encoding="utf-8")
    paths["report_md"].write_text(render_markdown(result.report), encoding="utf-8")
    paths["bundle"].write_text(json.dumps(result.bundle(), separators=(",", ":")), encoding="utf-8")
    paths["ascii"].write_text(render_ascii(result), encoding="utf-8")
    return paths


def render_ascii(result: MissionResult, step: int | None = None) -> str:
    """Text map: terrain, path walked, clues, decoys, chargers, WALL-E (W) and EVE (E)."""
    world = result.world
    grid = [list(row) for row in world["grid"]]
    upto = result.steps if step is None else result.steps[: step + 1]
    for rec in upto:
        x, y = rec["observation"]["position"]
        if grid[y][x] in ".~":
            grid[y][x] = "o"
    for c in world["clues"]:
        x, y = c["position"]
        grid[y][x] = "?"
    for d in world["decoys"]:
        x, y = d["position"]
        grid[y][x] = "D"
    for x, y in world["chargers"]:
        grid[y][x] = "C"
    ex, ey = world["eve"]["position"]
    grid[ey][ex] = "E"
    wx, wy = upto[-1]["observation"]["position"]
    grid[wy][wx] = "W"
    legend = "W WALL-E  E EVE  C charger  ? clue  D decoy  o path  # wall  ~ rubble"
    return "\n".join("".join(r) for r in grid) + "\n" + legend + "\n"
