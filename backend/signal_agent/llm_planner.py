"""LLM strategist: Claude picks the next sub-goal; classical code executes and guards it.

Claude is consulted only at decision points (when the previous directive has
been carried out), so a mission costs tens of calls, not hundreds. The
classical safety check always runs first and can override Claude, and any
directive that is infeasible, malformed or refused falls back to the
classical planner for that step. Every override is written to the trace.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from .environment import Action
from .memory import Decision, Memory
from .navigation import direction_to
from .planner import ClassicalPlanner, rank_targets, safety_check

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_MAX_CALLS = 40
MAX_TOKENS = 16000
CLIENT_TIMEOUT_S = 120.0

SYSTEM_PROMPT = """You are the mission strategist for WALL-E, a small rover searching a grid-shaped wasteland for EVE.
EVE's beacon is noisy, some transmitters are decoys that spoof her signal, clues can be misleading, and battery and time are limited.
A Bayesian belief map is maintained for you; the state you receive summarises it, along with ranked target cells that already account for travel and return cost.
Each turn, choose ONE directive:
- goto_and_scan: drive to `target` [x, y] and scan there (finds EVE, clues and decoys within the scan radius).
- scan_here: scan at the current cell.
- listen: take a radio fix (bearing + strength pings) from here; most useful after moving several cells from the last fix.
- investigate_clue: drive to a detected clue (`clue_id`) and read it.
- recharge: return to the nearest charger and charge to full.
- end_mission: stop and report (only when nothing reachable is worth searching).
Prefer high belief per battery, triangulate from new positions, read nearby clues, and never plan a trip WALL-E cannot return from.
Keep `reasoning` to one or two sentences explaining the trade-off."""


class Directive(BaseModel):
    action: Literal["goto_and_scan", "scan_here", "listen", "investigate_clue", "recharge", "end_mission"]
    target: list[int] | None = Field(None, description="[x, y] for goto_and_scan")
    clue_id: str | None = Field(None, description="clue id for investigate_clue")
    reasoning: str


class LLMPlanner:
    name = "llm"

    def __init__(self, model: str | None = None, max_calls: int | None = None, client: Any = None):
        self.model = model or os.environ.get("SIGNAL_LLM_MODEL", DEFAULT_MODEL)
        self.max_calls = max_calls if max_calls is not None else int(os.environ.get("SIGNAL_LLM_MAX_CALLS", DEFAULT_MAX_CALLS))
        self._client = client
        self._fallback = ClassicalPlanner()
        self._directive: Directive | None = None
        self._directive_tick = -1
        self.calls = 0
        self.overrides = 0

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - exercised only without the extra installed
                raise RuntimeError("The LLM planner needs the 'anthropic' package: pip install -e '.[llm]'") from exc
            self._client = anthropic.Anthropic(timeout=CLIENT_TIMEOUT_S)
        return self._client

    # ---------------------------------------------------------------- decide
    def decide(self, mem: Memory) -> Decision:
        guard = safety_check(mem)
        if guard:
            self._directive = None
            return guard
        if self._directive is None:
            if self.calls >= self.max_calls:
                return self._classical(mem, f"LLM call budget ({self.max_calls}) spent; classical planner takes over.")
            try:
                self._directive = self._ask(mem)
            except Exception as exc:  # noqa: BLE001 - any API failure must not crash the mission
                return self._classical(mem, f"LLM unavailable ({type(exc).__name__}: {exc}); classical fallback.")
            self._directive_tick = mem.tick
        directive = self._directive
        decision = self._execute(mem, directive)
        if decision is None:
            bad = directive
            self._directive = None
            return self._classical(mem, f"LLM directive {bad.action} {bad.target or bad.clue_id or ''} is infeasible here; classical override.")
        return decision

    def _classical(self, mem: Memory, why: str) -> Decision:
        self.overrides += 1
        d = self._fallback.decide(mem)
        return Decision(d.action, d.mode, d.goal, f"{why} {d.reasoning}", d.considered, source="llm->classical")

    # -------------------------------------------------------------- execute
    def _execute(self, mem: Memory, d: Directive) -> Decision | None:
        why = f"[Claude] {d.reasoning}"
        pos = mem.position
        if d.action == "listen":
            self._directive = None
            return Decision(Action("listen"), "listen", mem.goal, why, source="llm")
        if d.action == "scan_here":
            self._directive = None
            return Decision(Action("scan"), "search", pos, why, source="llm")
        if d.action == "end_mission":
            self._directive = None
            return Decision(Action("end"), "return", pos, why, source="llm")
        if d.action == "recharge":
            if pos in mem.chargers:
                if mem.battery >= mem.config.resources.battery_max - 1e-6:
                    self._directive = None
                    return None
                return Decision(Action("recharge"), "recharge", pos, why, source="llm")
            path = mem.to_charger().path(pos)
            return Decision(Action("move", direction_to(pos, path[0])), "recharge", path[-1], why, source="llm") if path else None
        if d.action == "investigate_clue":
            target = mem.pending_clues.get(d.clue_id or "")
            if target is None:
                return None
            if target == pos:
                self._directive = None
                return Decision(Action("inspect"), "investigate", pos, why, source="llm")
            return self._move_toward(mem, target, "investigate", why)
        # goto_and_scan
        if not d.target or len(d.target) != 2:
            return None
        target = (int(d.target[0]), int(d.target[1]))
        if not (0 <= target[0] < mem.known.width and 0 <= target[1] < mem.known.height):
            return None
        if target == pos:
            self._directive = None
            return Decision(Action("scan"), "search", pos, why, source="llm")
        return self._move_toward(mem, target, "search", why)

    def _move_toward(self, mem: Memory, target: tuple[int, int], mode: str, why: str) -> Decision | None:
        here = mem.from_here()
        cost = float(here.cost[target[1], target[0]])
        res = mem.config.resources
        if cost + mem.home_cost(target) + res.reserve > mem.battery:
            return None
        path = here.path(target)
        if not path:
            return None
        return Decision(Action("move", direction_to(mem.position, path[0])), mode, target, why, source="llm")

    # ------------------------------------------------------------------ ask
    def _ask(self, mem: Memory) -> Directive:
        self.calls += 1
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(self.situation(mem))}],
            output_format=Directive,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        if response.parsed_output is None:
            raise RuntimeError(f"no structured output (stop_reason={response.stop_reason})")
        return response.parsed_output

    @staticmethod
    def situation(mem: Memory) -> dict[str, Any]:
        """Compact, model-facing state. Built from WALL-E's memory only, never from the world."""
        here = mem.from_here()
        recent = [
            {"tick": e.tick, "kind": e.kind, "at": list(e.origin), **({k: v for k, v in e.data.items() if k != "signal"})}
            for e in mem.belief.evidence[-6:]
        ]
        return {
            "tick": mem.tick,
            "position": list(mem.position),
            "battery": round(mem.battery, 1),
            "battery_max": mem.config.resources.battery_max,
            "reserve": mem.config.resources.reserve,
            "battery_to_nearest_charger": round(mem.home_cost(), 1),
            "time_left": mem.time_left,
            "scan_radius": mem.config.sensors.scan_radius,
            "costs": mem.config.costs.model_dump(),
            "belief": {
                "top_cells": mem.belief.top_cells(6),
                "status": {k: round(v, 3) for k, v in mem.belief.status.items()},
                "entropy_bits": round(mem.belief.entropy_bits(), 2),
            },
            "ranked_targets": rank_targets(mem, 8),
            "pending_clues": [
                {"id": cid, "cell": list(p), "battery_to_reach": round(float(here.cost[p[1], p[0]]), 1)} for cid, p in mem.pending_clues.items()
            ],
            "clues_read": [{k: v for k, v in c.items() if k != "message"} | {"message": c.get("message")} for c in mem.inspected.values()],
            "known_decoys": [{"id": k, "cell": list(v)} for k, v in mem.decoys.items()],
            "ticks_since_listen": mem.tick - mem.last_listen_tick if mem.last_listen_pos else None,
            "cells_from_last_listen": None if mem.last_listen_pos is None else round(((mem.position[0] - mem.last_listen_pos[0]) ** 2 + (mem.position[1] - mem.last_listen_pos[1]) ** 2) ** 0.5, 1),
            "recent_evidence": recent,
        }
