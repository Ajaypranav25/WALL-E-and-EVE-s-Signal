"""Final mission report: evidence, inferred location/status, confidence and next step."""

from __future__ import annotations

from typing import Any

from . import physics
from .memory import Memory
from .navigation import dijkstra
from .world import World

STATUS_PLAYBOOK = {
    "active": "hail her on the beacon band and escort her back",
    "dormant": "wake her with a close-range beacon pulse, then tow her back to recharge",
    "damaged": "stabilise her, avoid jostling the damaged plating, and tow her back for repairs",
}
OUTCOME_TEXT = {
    "eve_located": "EVE located",
    "returned_to_base": "Returned to base without a confirmed sighting",
    "aborted_in_field": "Mission ended in the field without a confirmed sighting",
    "time_exhausted": "Time budget exhausted",
    "stranded": "WALL-E ran out of battery",
}


def _confidence(mem: Memory) -> tuple[float, str]:
    if mem.eve_found:
        p_status = max(mem.belief.status.values())
        return 0.99, f"high: location confirmed visually; status {p_status:.0%} by posterior"
    (mx, my), _ = mem.belief.map_estimate()
    p = mem.belief.mass_within((mx, my), mem.config.sensors.scan_radius)
    label = "high" if p >= 0.7 else "medium" if p >= 0.35 else "low"
    return p, f"{label} ({p:.0%} of belief within one scan of the best estimate)"


def _recommendation(mem: Memory, outcome: str, status: str) -> str:
    costs, res = mem.config.costs, mem.config.resources
    entry = mem.known.entry_costs(costs)
    if outcome == "stranded":
        return f"WALL-E is stranded at {mem.position} with an empty battery. Dispatch a recovery run from the nearest charger before resuming the search."
    if mem.eve_found:
        eve = tuple(mem.eve_found["position"])
        to_eve = float(dijkstra(entry, [mem.position]).cost[eve[1], eve[0]])
        back = mem.home_cost(eve)
        need = to_eve + back + res.reserve
        plan = STATUS_PLAYBOOK[status]
        if mem.battery >= need:
            return f"Move to EVE at {eve} (~{to_eve:.0f} battery) and {plan}; the round trip needs ~{need:.0f} and WALL-E has {mem.battery:.0f}."
        charger = min(mem.chargers, key=lambda c: physics.distance(c, mem.position))
        return f"Recharge at {charger} first (round trip needs ~{need:.0f}, battery is {mem.battery:.0f}), then go to EVE at {eve} and {plan}."
    (mx, my), _ = mem.belief.map_estimate()
    region = mem.belief.credible_region(0.9)
    xs, ys = [c[0] for c in region], [c[1] for c in region]
    decoy_note = f" Ignore the known decoy transmitter(s) at {', '.join(str(p) for p in mem.decoys.values())}." if mem.decoys else ""
    return (
        f"Launch a fully charged follow-up search toward {(mx, my)}; the 90% credible region spans x {min(xs)}-{max(xs)}, "
        f"y {min(ys)}-{max(ys)} ({len(region)} cells). Most likely status: {status}.{decoy_note}"
    )


def build_report(mem: Memory, world: World, outcome: str, planner: str, recorder, battery_used: float, distance: int, recharges: int) -> dict[str, Any]:
    # The posterior already folds in the visual status read (it is ~90% reliable), so
    # signal strength history and clues can outvote a single misread.
    status_probs = mem.belief.status
    status = max(status_probs, key=status_probs.get)
    (mx, my), p_map = mem.belief.map_estimate()
    location = tuple(mem.eve_found["position"]) if mem.eve_found else (mx, my)
    conf_value, conf_label = _confidence(mem)
    listens = [r for r in recorder.records if r.get("action") and r["action"]["kind"] == "listen"]
    pings = sum(len(r["observation"].get("pings", [])) for r in listens)
    return {
        "mission": {
            "name": mem.config.name,
            "seed": mem.config.seed,
            "planner": planner,
            "outcome": outcome,
            "outcome_text": OUTCOME_TEXT.get(outcome, outcome),
            "steps": len(recorder.records) - 1,
            "time_used": mem.time_used,
            "time_limit": mem.config.resources.time_limit,
            "battery_left": round(mem.battery, 1),
            "battery_used": round(battery_used, 1),
            "distance_travelled": distance,
            "recharges": recharges,
        },
        "evidence": {
            "initial_signal": world.initial_signal.model_dump(),
            "clues_read": list(mem.inspected.values()),
            "clues_detected_unread": [{"id": k, "position": list(v)} for k, v in mem.pending_clues.items()],
            "listens": len(listens),
            "pings_heard": pings,
            "suspicious_pings": mem.suspicious_pings,
            "decoys_identified": [{"id": k, "position": list(v)} for k, v in mem.decoys.items()],
            "eve_sighting": mem.eve_found,
        },
        "inference": {
            "location": list(location),
            "map_probability": round(p_map, 4),
            "credible_region_90_cells": len(mem.belief.credible_region(0.9)),
            "status": status,
            "status_probabilities": {k: round(v, 3) for k, v in status_probs.items()},
            "confidence": round(conf_value, 3),
            "confidence_text": conf_label,
        },
        "recommended_next_step": _recommendation(mem, outcome, status),
        "strategy_changes": recorder.strategy_changes,
        "ground_truth": {
            "_note": "Evaluation only; never visible to the agent.",
            "eve_position": list(world.eve_position),
            "eve_status": world.eve_status,
            "location_error_cells": round(physics.distance(location, world.eve_position), 2),
            "status_correct": status == world.eve_status,
            "decoys": [{"id": d.id, "position": list(d.position)} for d in world.decoys],
            "clues": [{"id": c.id, "kind": c.kind, "position": list(c.position), "misleading": c.misleading} for c in world.clues],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    m, ev, inf, gt = report["mission"], report["evidence"], report["inference"], report["ground_truth"]
    lines = [
        f"# Mission report: {m['name']}",
        "",
        f"**Outcome:** {m['outcome_text']}  ",
        f"**Planner:** {m['planner']} · **Seed:** {m['seed']} · **Steps:** {m['steps']} · **Time:** {m['time_used']}/{m['time_limit']}  ",
        f"**Battery:** {m['battery_used']} used, {m['battery_left']} left, {m['recharges']} recharge ticks · **Distance:** {m['distance_travelled']} cells",
        "",
        "## Inferred location and status",
        "",
        f"- Location: **{tuple(inf['location'])}** (cell probability {inf['map_probability']:.1%}, 90% region {inf['credible_region_90_cells']} cells)",
        f"- Status: **{inf['status']}** ({', '.join(f'{k} {v:.0%}' for k, v in inf['status_probabilities'].items())})",
        f"- Confidence: {inf['confidence_text']}",
        "",
        "## Recommended next step",
        "",
        report["recommended_next_step"],
        "",
        "## Evidence found",
        "",
    ]
    sig = ev["initial_signal"]
    where = f"bearing {sig['bearing_deg']}°" if sig.get("bearing_deg") is not None else f"near {tuple(sig['coordinates'])} ±{sig['uncertainty']}"
    lines.append(f"- Briefing signal: {where}, {sig.get('strength_dbm')} dBm, t={sig['timestamp']}")
    lines.append(f"- Listens: {ev['listens']}, pings heard: {ev['pings_heard']}, flagged as suspicious: {ev['suspicious_pings']}")
    for c in ev["clues_read"]:
        lines.append(f"- {c['id']} ({c['kind']}) at {tuple(c['position'])}: {c['message']}")
    for c in ev["clues_detected_unread"]:
        lines.append(f"- {c['id']} detected at {tuple(c['position'])} but not read")
    for d in ev["decoys_identified"]:
        lines.append(f"- Decoy transmitter {d['id']} identified at {tuple(d['position'])}")
    if ev["eve_sighting"]:
        seen = ev["eve_sighting"]
        lines.append(f"- EVE sighted at {tuple(seen['position'])}, status read: {seen['status']}")
        if seen["status"] != inf["status"]:
            lines.append(f"  - The visual read disagrees with the accumulated evidence; signal strength history favours **{inf['status']}**.")
    lines += ["", "## Strategy changes", ""]
    if not report["strategy_changes"]:
        lines.append("- None")
    for ch in report["strategy_changes"]:
        lines.append(f"- step {ch['step']}: {ch['from']} → {ch['to']}: {ch['reason']}")
    lines += [
        "",
        "## Ground truth (evaluation only)",
        "",
        f"- EVE was at {tuple(gt['eve_position'])}, status {gt['eve_status']}; location error {gt['location_error_cells']} cells; status {'correct' if gt['status_correct'] else 'wrong'}",
        f"- Decoys: {', '.join(str(tuple(d['position'])) for d in gt['decoys']) or 'none'}",
        "",
    ]
    return "\n".join(lines)
