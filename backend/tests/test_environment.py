import pytest

from signal_agent.environment import Action, Environment
from signal_agent.world import Clue


def test_move_spends_battery_and_time(small_config):
    env = Environment(small_config)
    obs = env.step(Action("move", "N"))
    assert obs.position == (0, 6)
    assert obs.battery == pytest.approx(79.0)
    assert obs.time_used == 1


def test_blocked_move_keeps_position(small_config):
    env = Environment(small_config)
    obs = env.step(Action("move", "W"))
    assert obs.result == "blocked" and obs.position == (0, 7)


def test_move_requires_direction():
    with pytest.raises(ValueError):
        Action("move")


def test_listen_returns_pings_from_eve(small_config):
    env = Environment(small_config)
    heard = [p for _ in range(10) for p in env.step(Action("listen")).pings]
    assert heard, "an active EVE 11 cells away should be audible"
    assert all(-120 < p["strength_dbm"] < 0 and 0 <= p["bearing_deg"] < 360 for p in heard)


def test_recharge_only_at_charger(small_config):
    env = Environment(small_config)
    env.step(Action("move", "N"))
    assert env.step(Action("recharge")).result == "no charger here"
    env.step(Action("move", "S"))
    assert env.step(Action("recharge")).battery == pytest.approx(80.0)


def test_inspect_reveals_clue_content(small_config):
    env = Environment(small_config)
    env._state.position = (6, 4)
    obs = env.step(Action("inspect"))
    assert obs.clue["kind"] == "tracks" and "bearing_deg" in obs.clue
    env._state.position = (5, 5)
    assert env.step(Action("inspect")).result == "nothing to inspect here"


def test_scan_finds_eve_and_ends_mission(small_config):
    env = Environment(small_config, noise_seed=0)
    env._state.position = (10, 2)
    for _ in range(5):
        obs = env.step(Action("scan"))
        if obs.done:
            break
    assert obs.outcome == "eve_located"
    assert any(d["type"] == "eve" for d in obs.detections)
    with pytest.raises(RuntimeError):
        env.step(Action("scan"))


def test_running_dry_strands_wall_e(small_config):
    env = Environment(small_config)
    env._state.battery = 1.0
    obs = env.step(Action("scan"))
    assert obs.done and obs.outcome == "stranded" and obs.battery == 0


def test_time_limit_ends_mission(small_config):
    cfg = small_config.model_copy(update={"resources": small_config.resources.model_copy(update={"time_limit": 3})})
    env = Environment(cfg)
    for _ in range(3):
        obs = env.step(Action("listen"))
    assert obs.done and obs.outcome == "time_exhausted"


def test_end_at_base(small_config):
    env = Environment(small_config)
    assert env.step(Action("end")).outcome == "returned_to_base"


@pytest.mark.parametrize("kind,field", [("log_fragment", "sector"), ("scorch_mark", "distance_estimate"), ("plant", "status_hint")])
def test_every_clue_kind_has_payload(small_config, kind, field):
    env = Environment(small_config)
    content = env._clue_content(Clue("c", kind, (3, 3), misleading=False))
    assert field in content and content["message"]


def test_misleading_clue_still_well_formed(small_config):
    env = Environment(small_config)
    content = env._clue_content(Clue("c", "tracks", (3, 3), misleading=True))
    assert 0 <= content["bearing_deg"] < 360
