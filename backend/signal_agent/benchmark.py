"""Generalisation benchmark: many seeded random missions, several planners, one table."""

from __future__ import annotations

import statistics
import time
from typing import Any

import numpy as np

from .config import MissionConfig
from .mission import run_mission

MAX_BENCH_MISSIONS = 500


def random_config(seed: int) -> MissionConfig:
    """A randomised but reproducible mission. Harder than the defaults: noisier, decoys, fog."""
    rng = np.random.default_rng(10_000 + seed)
    return MissionConfig.model_validate({
        "name": f"bench-{seed}",
        "seed": seed,
        "map": {
            "width": int(rng.integers(22, 33)),
            "height": int(rng.integers(16, 23)),
            "wall_density": float(rng.uniform(0.08, 0.16)),
            "rubble_density": float(rng.uniform(0.08, 0.2)),
            "known": bool(rng.random() < 0.7),
        },
        "resources": {"battery_max": float(rng.uniform(70, 110)), "time_limit": int(rng.integers(260, 380)), "reserve": 6},
        "sensors": {"bearing_noise_deg": float(rng.uniform(10, 22)), "strength_noise_db": float(rng.uniform(2.5, 5))},
        "clue_count": int(rng.integers(3, 8)),
        "misleading_rate": float(rng.uniform(0.05, 0.2)),
        "decoy_count": int(rng.integers(0, 3)),
    })


def run_benchmark(n: int = 30, seed: int = 0, planners: tuple[str, ...] = ("classical", "greedy"), **planner_kwargs: Any) -> dict[str, Any]:
    if not 1 <= n <= MAX_BENCH_MISSIONS:
        raise ValueError(f"n must be between 1 and {MAX_BENCH_MISSIONS}")
    configs = [random_config(seed + i) for i in range(n)]
    results: dict[str, Any] = {}
    for planner in planners:
        rows = []
        started = time.perf_counter()
        for cfg in configs:
            kwargs = planner_kwargs if planner == "llm" else {}
            res = run_mission(cfg, planner, **kwargs)
            m, gt = res.report["mission"], res.report["ground_truth"]
            rows.append({
                "seed": cfg.seed,
                "outcome": res.outcome,
                "found": res.outcome == "eve_located",
                "stranded": res.outcome == "stranded",
                "time_used": m["time_used"],
                "battery_used": m["battery_used"],
                "steps": m["steps"],
                "error": gt["location_error_cells"],
                "status_correct": gt["status_correct"],
                "decoys": len(gt["decoys"]),
                "decoys_identified": len(res.report["evidence"]["decoys_identified"]),
                "strategy_changes": len(res.report["strategy_changes"]),
            })
        results[planner] = {"summary": _summarise(rows), "runs": rows, "seconds": round(time.perf_counter() - started, 2)}
    return {"n": n, "seed": seed, "planners": list(planners), "results": results}


def _summarise(rows: list[dict[str, Any]]) -> dict[str, float]:
    found = [r for r in rows if r["found"]]
    mean = lambda xs: round(statistics.fmean(xs), 2) if xs else None  # noqa: E731
    return {
        "success_rate": round(len(found) / len(rows), 3),
        "stranded_rate": round(sum(r["stranded"] for r in rows) / len(rows), 3),
        "mean_time_when_found": mean([r["time_used"] for r in found]),
        "mean_battery_when_found": mean([r["battery_used"] for r in found]),
        "mean_location_error": mean([r["error"] for r in rows]),
        "status_accuracy": round(sum(r["status_correct"] for r in rows) / len(rows), 3),
        "decoy_missions_solved": round(
            sum(r["found"] for r in rows if r["decoys"]) / max(1, sum(1 for r in rows if r["decoys"])), 3
        ),
    }


def render_table(bench: dict[str, Any]) -> str:
    cols = ["success_rate", "stranded_rate", "mean_time_when_found", "mean_battery_when_found", "mean_location_error", "status_accuracy", "decoy_missions_solved"]
    head = "| planner | " + " | ".join(cols) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    lines = [head, sep]
    for name, res in bench["results"].items():
        s = res["summary"]
        lines.append(f"| {name} | " + " | ".join(str(s[c]) for c in cols) + " |")
    return "\n".join(lines)
