import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signal_agent.config import MissionConfig  # noqa: E402

LAYOUT = [
    "............",
    "............",
    "....##......",
    "....##......",
    "............",
    "....~~~.....",
    "............",
    "............",
]

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def small_config() -> MissionConfig:
    """Tiny deterministic world with everything placed explicitly."""
    return MissionConfig.model_validate({
        "name": "test",
        "seed": 1,
        "map": {"layout": LAYOUT},
        "start": [0, 7],
        "chargers": [[0, 7]],
        "eve": {"position": [10, 1], "status": "active"},
        "initial_signal": {"bearing_deg": 50, "strength_dbm": -62, "timestamp": -5},
        "resources": {"battery_max": 80, "time_limit": 200},
        "clues": [{"kind": "tracks", "position": [6, 4]}, {"kind": "plant", "position": [8, 2]}],
        "decoys": [],
    })


@pytest.fixture
def config_dir() -> Path:
    return BACKEND / "configs"
