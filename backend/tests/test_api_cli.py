import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from signal_agent.api import RateLimiter, create_app
from signal_agent.benchmark import random_config, render_table, run_benchmark
from signal_agent.cli import main


@pytest.fixture
def client(config_dir):
    return TestClient(create_app(config_dir))


def test_health_and_config_listing(client):
    assert client.get("/api/health").json() == {"success": True, "data": {"status": "ok"}, "error": None}
    names = {c["name"] for c in client.get("/api/configs").json()["data"]}
    assert {"sample_mission", "decoy_storm", "hand_drawn"} <= names


def test_get_config_and_errors(client):
    body = client.get("/api/configs/hand_drawn").json()
    assert body["success"] and "layout" in body["data"]["source"]
    missing = client.get("/api/configs/nope")
    assert missing.status_code == 404 and missing.json()["success"] is False
    assert client.get("/api/configs/bad.name").status_code == 400


def test_run_mission_and_fetch(client):
    res = client.post("/api/missions", json={"config_name": "hand_drawn"}).json()
    assert res["success"]
    bundle = res["data"]
    assert bundle["world"]["width"] == 21 and bundle["steps"] and bundle["report"]["mission"]["outcome"]
    assert client.get(f"/api/runs/{bundle['id']}").json()["data"]["id"] == bundle["id"]
    assert client.get("/api/runs/missing").status_code == 404


def test_run_random_seed_and_reseeded_config(client):
    assert client.post("/api/missions", json={"seed": 5}).json()["success"]
    assert client.post("/api/missions", json={"config_name": "hand_drawn", "seed": 9}).json()["data"]["report"]["mission"]["seed"] == 9


def test_run_inline_config_and_validation(client):
    ok = client.post("/api/missions", json={"config": {"seed": 3, "map": {"width": 16, "height": 12}}, "planner": "greedy"})
    assert ok.status_code == 200
    bad = client.post("/api/missions", json={"config": {"map": {"width": 1000}}})
    assert bad.status_code == 422 and bad.json()["success"] is False
    assert client.post("/api/missions", json={"config_name": "hand_drawn", "config": {}}).status_code == 422
    assert client.post("/api/missions", json={"config_name": "../etc"}).status_code == 422
    wall = client.post("/api/missions", json={"config": {"start": [0, 0], "map": {"layout": ["#......."] + ["........"] * 7}}})
    assert wall.status_code == 422 and "wall" in wall.json()["error"]


def test_benchmark_endpoint(client):
    res = client.post("/api/benchmark", json={"n": 2, "planners": ["classical", "greedy"]}).json()
    assert set(res["data"]["results"]) == {"classical", "greedy"}
    assert client.post("/api/benchmark", json={"n": 5000}).status_code == 422


def test_rate_limiter_blocks_bursts():
    limiter = RateLimiter(2)
    req = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"))
    limiter(req)
    limiter(req)
    with pytest.raises(HTTPException):
        limiter(req)


def test_benchmark_summary_and_table():
    bench = run_benchmark(2, planners=("classical",))
    assert "| classical |" in render_table(bench)
    assert random_config(1) == random_config(1)
    with pytest.raises(ValueError):
        run_benchmark(0)


def test_cli_run_validate_bench(tmp_path, config_dir, capsys):
    assert main(["validate", str(config_dir / "hand_drawn.yaml")]) == 0
    assert main(["run", str(config_dir / "hand_drawn.yaml"), "--out", str(tmp_path / "run"), "--ascii"]) == 0
    assert (tmp_path / "run" / "trace.jsonl").exists()
    out = tmp_path / "bench.json"
    assert main(["bench", "--n", "2", "--planners", "classical", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["n"] == 2
    assert main(["run", str(tmp_path / "missing.yaml")]) == 2
    assert "error" in capsys.readouterr().err
