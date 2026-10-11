"""Regression tests for bugs found in code review."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from signal_agent import physics
from signal_agent.agent import Agent
from signal_agent.api import create_app
from signal_agent.belief import Belief, Evidence
from signal_agent.config import MissionConfig, Sensors, load_config
from signal_agent.environment import Action, Environment
from signal_agent.llm_planner import Directive, LLMPlanner
from signal_agent.mission import run_mission, write_outputs
from signal_agent.world import _generate_initial_signal


def test_llm_recharge_at_full_charger_falls_back_instead_of_crashing(small_config):
    client = SimpleNamespace(messages=SimpleNamespace(parse=lambda **_: SimpleNamespace(stop_reason="end_turn", parsed_output=Directive(action="recharge", reasoning="r"))))
    planner = LLMPlanner(client=client, max_calls=2)
    d = planner.decide(Agent.create(small_config, planner).mem)
    assert d.source == "llm->classical"


def test_duplicate_clue_cells_rejected(small_config):
    data = small_config.model_dump()
    data["clues"] = [{"kind": "tracks", "position": (3, 3)}, {"kind": "plant", "position": (3, 3)}]
    with pytest.raises(ValidationError, match="share a cell"):
        MissionConfig.model_validate(data)


def test_inspect_moves_on_to_unread_clue_on_same_cell(small_config):
    from signal_agent.world import Clue

    env = Environment(small_config)
    world = env.world
    object.__setattr__(world, "clues", (Clue("a", "tracks", (2, 2), False), Clue("b", "plant", (2, 2), False)))
    env._state.position = (2, 2)
    first = env.step(Action("inspect")).clue["id"]
    second = env.step(Action("inspect")).clue["id"]
    assert {first, second} == {"a", "b"}


def test_heard_ping_not_penalised_twice_for_audibility():
    # With a high receiver threshold, a strong ping should still point at a far source.
    sensors = Sensors(sensitivity_dbm=-60.0)
    b = Belief(30, 10, sensors, np.ones((10, 30), dtype=bool))
    origin, eve = (0, 5), (20, 5)
    ping = {"bearing_deg": physics.bearing_deg(origin, eve), "strength_dbm": -60.0}
    b.add(Evidence("pings", origin, {"pings": [ping]}, 0))
    (x, _), _ = b.map_estimate()
    assert x >= 10


def test_generated_bearing_never_rounds_to_360():
    class Rng:
        def normal(self, *_):
            return -0.04  # true bearing 0 -> 359.96 -> rounds to 360.0 without the wrap

        def integers(self, *_):
            return 10

    sig = _generate_initial_signal(Rng(), (5, 10), (5, 0), "active", 10.0)
    assert 0 <= sig.bearing_deg < 360


def test_trace_is_strict_json_when_few_cells_are_feasible(tmp_path):
    cfg = MissionConfig.model_validate({"seed": 3, "resources": {"battery_max": 10, "time_limit": 60}})
    result = run_mission(cfg)
    paths = write_outputs(result, tmp_path)
    for line in paths["trace"].read_text(encoding="utf-8").splitlines():
        json.loads(line, parse_constant=lambda c: pytest.fail(f"non-finite {c} in trace"))


def test_bad_yaml_is_a_value_error(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("name: [unclosed", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_config(bad)
    bad_json = tmp_path / "broken.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_config(bad_json)


def test_api_lists_configs_even_with_a_broken_file(tmp_path, config_dir):
    (tmp_path / "ok.yaml").write_text((config_dir / "hand_drawn.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "broken.yaml").write_text("name: [unclosed", encoding="utf-8")
    res = TestClient(create_app(tmp_path)).get("/api/configs")
    assert res.status_code == 200
    items = {i["name"]: i for i in res.json()["data"]}
    assert "error" in items["broken"] and "error" not in items["ok"]


def test_api_rejects_oversized_inline_configs(config_dir):
    client = TestClient(create_app(config_dir))
    big = client.post("/api/missions", json={"config": {"map": {"width": 64, "height": 64}}})
    assert big.status_code == 422 and "CLI-only" in big.json()["error"]
    long = client.post("/api/missions", json={"config": {"resources": {"time_limit": 20000}}})
    assert long.status_code == 422
    too_many = client.post("/api/missions", json={"config": {"decoys": [{"position": [1, 1]}] * 7}})
    assert too_many.status_code == 422


def test_api_llm_planner_is_opt_in(config_dir, monkeypatch):
    client = TestClient(create_app(config_dir))
    monkeypatch.delenv("SIGNAL_API_ALLOW_LLM", raising=False)
    assert client.post("/api/missions", json={"config_name": "hand_drawn", "planner": "llm"}).status_code == 403
    assert client.post("/api/benchmark", json={"n": 1, "planners": ["llm"]}).status_code == 403
