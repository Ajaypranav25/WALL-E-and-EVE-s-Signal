import pytest

from signal_agent.agent import Agent
from signal_agent.config import MissionConfig
from signal_agent.mission import render_ascii, run_mission, write_outputs
from signal_agent.planner import ClassicalPlanner, GreedyPlanner, safety_check
from signal_agent.report import _recommendation


def test_classical_finds_eve_in_small_world(small_config):
    result = run_mission(small_config, "classical")
    assert result.outcome == "eve_located"
    assert result.report["inference"]["location"] == [10, 1]


def test_trace_logs_every_step_with_reasoning(small_config):
    steps = run_mission(small_config, "classical").steps
    assert steps[0]["decision"]["mode"] == "start"
    for rec in steps[1:]:
        assert rec["action"]["kind"] in {"move", "scan", "listen", "inspect", "recharge", "end"}
        assert rec["decision"]["reasoning"]
        assert "observation" in rec and "state" in rec
        assert len(rec["belief"]) == 12 * 8


def test_safety_check_sends_low_battery_home(small_config):
    mem = Agent.create(small_config).mem
    mem.position, mem.battery = (8, 3), 9.0
    d = safety_check(mem)
    assert d is not None and d.mode == "recharge" and d.action.kind == "move"


def test_safety_check_recharges_at_charger(small_config):
    mem = Agent.create(small_config).mem
    mem.battery = 2.0
    assert safety_check(mem).action.kind == "recharge"
    mem.mode, mem.battery = "recharge", 50.0
    assert safety_check(mem).action.kind == "recharge"


def test_safety_check_returns_when_time_runs_out(small_config):
    mem = Agent.create(small_config).mem
    mem.position, mem.time_used = (6, 6), small_config.resources.time_limit - 6
    assert safety_check(mem).mode == "return"
    mem.position, mem.time_used = (0, 7), small_config.resources.time_limit - 2
    assert safety_check(mem).action.kind == "end"


def test_planner_inspects_clue_underfoot(small_config):
    mem = Agent.create(small_config).mem
    mem.pending_clues["clue-1"] = mem.position
    assert ClassicalPlanner().decide(mem).action.kind == "inspect"


def test_planner_detours_to_detected_clue(small_config):
    mem = Agent.create(small_config).mem
    mem.last_listen_pos, mem.last_listen_tick = mem.position, 0
    mem.pending_clues["clue-1"] = (2, 6)
    d = ClassicalPlanner().decide(mem)
    assert d.mode == "investigate" and d.goal == (2, 6)


def test_first_decision_is_to_listen(small_config):
    assert ClassicalPlanner().decide(Agent.create(small_config).mem).action.kind == "listen"


def test_planner_scans_when_belief_is_in_range(small_config):
    from signal_agent.belief import Evidence

    mem = Agent.create(small_config).mem
    mem.last_listen_pos, mem.last_listen_tick = mem.position, 0
    mem.position = (9, 2)
    mem.belief.add(Evidence("clue", (9, 2), {"distance_estimate": 1.0}, 0))
    assert ClassicalPlanner().decide(mem).action.kind == "scan"


def test_no_goal_heads_home_to_extend_range(small_config):
    mem = Agent.create(small_config).mem
    mem.position, mem.battery = (5, 6), 40.0
    d = ClassicalPlanner()._no_goal(mem)
    assert d.mode == "recharge"
    mem.battery = 80.0
    assert ClassicalPlanner()._no_goal(mem).mode == "return"


def test_greedy_runs_to_completion(small_config):
    result = run_mission(small_config, GreedyPlanner())
    assert result.outcome in {"eve_located", "returned_to_base", "time_exhausted", "aborted_in_field"}
    assert result.report["mission"]["planner"] == "greedy"


def test_unknown_planner_rejected(small_config):
    with pytest.raises(ValueError, match="unknown planner"):
        Agent.create(small_config, "astrology")


def test_decoy_mission_still_finds_eve():
    cfg = MissionConfig.model_validate({
        "seed": 4,
        "map": {"width": 24, "height": 16, "wall_density": 0.05, "rubble_density": 0.05},
        "start": [1, 14],
        "eve": {"position": [21, 2], "status": "active"},
        "decoys": [{"position": [8, 6], "power_dbm": -34}],
        "initial_signal": {"bearing_deg": 20, "strength_dbm": -70, "timestamp": -20},
    })
    assert run_mission(cfg, "classical").outcome == "eve_located"


def test_fog_of_war_mission_completes():
    cfg = MissionConfig.model_validate({"seed": 9, "map": {"known": False}, "decoy_count": 1})
    assert run_mission(cfg, "classical").outcome == "eve_located"


def test_outputs_written(tmp_path, small_config):
    result = run_mission(small_config)
    paths = write_outputs(result, tmp_path)
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0
    assert "W WALL-E" in render_ascii(result, step=3)
    md = paths["report_md"].read_text(encoding="utf-8")
    assert "Recommended next step" in md and "Ground truth" in md


def test_report_fields(small_config):
    report = run_mission(small_config).report
    assert set(report) >= {"mission", "evidence", "inference", "recommended_next_step", "strategy_changes", "ground_truth"}
    assert 0 <= report["inference"]["confidence"] <= 1
    assert sum(report["inference"]["status_probabilities"].values()) == pytest.approx(1, abs=0.01)


def test_stranded_report_recommends_recovery(small_config):
    mem = Agent.create(small_config).mem
    assert "stranded" in _recommendation(mem, "stranded", "active")


def test_inconclusive_report_recommends_follow_up(small_config):
    mem = Agent.create(small_config).mem
    mem.decoys["decoy-1"] = (3, 3)
    text = _recommendation(mem, "returned_to_base", "active")
    assert "follow-up" in text and "decoy" in text


def test_found_report_recharges_first_when_short(small_config):
    mem = Agent.create(small_config).mem
    mem.eve_found = {"position": [10, 1], "status": "active"}
    mem.battery = 5.0
    assert _recommendation(mem, "eve_located", "active").startswith("Recharge")
