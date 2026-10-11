import json

import pytest
from pydantic import ValidationError

from signal_agent.config import MissionConfig, load_config


def test_defaults_are_valid():
    cfg = MissionConfig()
    assert cfg.resources.start == cfg.resources.battery_max


@pytest.mark.parametrize("name", ["sample_mission.yaml", "decoy_storm.json", "hand_drawn.yaml"])
def test_sample_configs_load(config_dir, name):
    cfg = load_config(config_dir / name)
    assert cfg.name


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        MissionConfig.model_validate({"surprise": 1})


def test_initial_signal_needs_bearing_or_coordinates():
    with pytest.raises(ValidationError):
        MissionConfig.model_validate({"initial_signal": {"strength_dbm": -60}})


def test_battery_start_cannot_exceed_max():
    with pytest.raises(ValidationError):
        MissionConfig.model_validate({"resources": {"battery_max": 50, "battery_start": 60}})


def test_layout_rejects_ragged_rows_and_bad_symbols():
    with pytest.raises(ValidationError):
        MissionConfig.model_validate({"map": {"layout": ["........", "......."] + ["........"] * 6}})
    with pytest.raises(ValidationError):
        MissionConfig.model_validate({"map": {"layout": ["....X..."] + ["........"] * 7}})


def test_load_config_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")
    bad = tmp_path / "x.txt"
    bad.write_text("{}")
    with pytest.raises(ValueError, match="unsupported"):
        load_config(bad)
    lst = tmp_path / "x.json"
    lst.write_text(json.dumps([1, 2]))
    with pytest.raises(ValueError, match="mapping"):
        load_config(lst)
