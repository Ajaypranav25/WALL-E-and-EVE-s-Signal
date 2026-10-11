"""Command line: run a mission, benchmark planners, validate configs, serve the API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import load_config


def _cmd_run(args: argparse.Namespace) -> int:
    from .mission import render_ascii, run_mission, write_outputs

    cfg = load_config(args.config)
    result = run_mission(cfg, args.planner)
    out = Path(args.out or f"runs/{Path(args.config).stem}")
    paths = write_outputs(result, out)
    m, inf = result.report["mission"], result.report["inference"]
    if args.ascii:
        print(render_ascii(result))
    print(f"{m['outcome_text']} in {m['steps']} steps ({m['time_used']}/{m['time_limit']} ticks, {m['battery_used']} battery used)")
    print(f"Inferred EVE at {tuple(inf['location'])}, status {inf['status']}, confidence {inf['confidence_text']}")
    print(f"Next: {result.report['recommended_next_step']}")
    print(f"Trace -> {paths['trace']}\nReport -> {paths['report_md']}\nVisualizer bundle -> {paths['bundle']}")
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    from .benchmark import render_table, run_benchmark

    planners = tuple(p.strip() for p in args.planners.split(",") if p.strip())
    bench = run_benchmark(args.n, args.seed, planners)
    print(render_table(bench))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(bench, indent=2), encoding="utf-8")
        print(f"Saved -> {args.out}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from .world import build_world

    cfg = load_config(args.config)
    world = build_world(cfg)
    print(f"OK: {cfg.name!r} {world.width}x{world.height}, {len(world.clues)} clues, {len(world.decoys)} decoys, {len(world.chargers)} chargers")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("signal_agent.api:app", host=args.host, port=args.port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="walle", description="WALL-E and EVE's Signal: autonomous search agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one mission and write trace + report")
    run.add_argument("config", help="mission config (.yaml/.yml/.json)")
    run.add_argument("--planner", choices=["classical", "greedy", "llm"], default="classical")
    run.add_argument("--out", help="output directory (default runs/<config name>)")
    run.add_argument("--ascii", action="store_true", help="print the final map")
    run.set_defaults(func=_cmd_run)

    bench = sub.add_parser("bench", help="benchmark planners over random missions")
    bench.add_argument("--n", type=int, default=30)
    bench.add_argument("--seed", type=int, default=0)
    bench.add_argument("--planners", default="classical,greedy", help="comma list of classical,greedy,llm")
    bench.add_argument("--out", help="save JSON results here")
    bench.set_defaults(func=_cmd_bench)

    val = sub.add_parser("validate", help="check a config and build its world")
    val.add_argument("config")
    val.set_defaults(func=_cmd_validate)

    serve = sub.add_parser("serve", help="start the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
