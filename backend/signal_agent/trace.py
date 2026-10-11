"""Full action trace: every action, observation, decision, reasoning and belief snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .belief import Belief
from .memory import Decision, Memory


def belief_snapshot(belief: Belief) -> list[int]:
    """Belief marginal in units of 1e-4, row-major, to keep traces compact."""
    return [int(v) for v in np.rint(belief.location.ravel() * 10_000)]


@dataclass
class TraceRecorder:
    records: list[dict[str, Any]] = field(default_factory=list)
    strategy_changes: list[dict[str, Any]] = field(default_factory=list)
    last_search_goal: tuple[int, int] | None = None

    def start(self, mem: Memory, obs, notes: list[str]) -> None:
        self.records.append({
            "step": 0,
            "tick": 0,
            "action": None,
            "decision": {"mode": "start", "goal": None, "reasoning": "Mission brief loaded; prior built from the last received signal.", "source": "brief"},
            "observation": obs.to_dict(),
            "notes": notes,
            "state": mem.summary(),
            "top_cells": mem.belief.top_cells(5),
            "belief": belief_snapshot(mem.belief),
        })

    def step(self, mem: Memory, d: Decision, obs, notes: list[str], change: dict[str, Any] | None) -> None:
        step_no = len(self.records)
        if d.mode == "search" and d.goal:
            self.last_search_goal = d.goal
        record = {
            "step": step_no,
            "tick": obs.tick,
            "action": d.action.to_dict(),
            "decision": {
                "mode": d.mode,
                "goal": list(d.goal) if d.goal else None,
                "reasoning": d.reasoning,
                "source": d.source,
                "considered": list(d.considered),
            },
            "observation": obs.to_dict(),
            "notes": notes,
            "state": mem.summary(),
            "top_cells": mem.belief.top_cells(5),
            "belief": belief_snapshot(mem.belief),
        }
        if change:
            change = {**change, "step": step_no, "tick": obs.tick}
            record["strategy_change"] = change
            self.strategy_changes.append(change)
        self.records.append(record)

    def write_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for rec in self.records:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
