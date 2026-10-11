import numpy as np
import pytest

from signal_agent import physics
from signal_agent.config import MissionConfig
from signal_agent.world import WALL, build_world, reachable_cells


def test_same_seed_same_world():
    a, b = build_world(MissionConfig(seed=11, decoy_count=2)), build_world(MissionConfig(seed=11, decoy_count=2))
    assert np.array_equal(a.grid, b.grid)
    assert a.eve_position == b.eve_position and a.clues == b.clues and a.decoys == b.decoys


def test_generated_world_is_fully_reachable():
    world = build_world(MissionConfig(seed=5))
    reach = reachable_cells(world.grid, world.start)
    free = {(x, y) for y in range(world.height) for x in range(world.width) if world.grid[y, x] != WALL}
    assert free == reach
    assert world.eve_position in reach and all(c in reach for c in world.chargers)


def test_grid_is_read_only():
    world = build_world(MissionConfig(seed=2))
    with pytest.raises(ValueError):
        world.grid[0, 0] = WALL


def test_explicit_placements_are_respected(small_config):
    world = build_world(small_config)
    assert world.eve_position == (10, 1) and world.eve_status == "active"
    assert [c.position for c in world.clues] == [(6, 4), (8, 2)]
    assert world.chargers == ((0, 7),)


def test_rejects_entity_inside_wall(small_config):
    cfg = small_config.model_copy(update={"eve": small_config.eve.model_copy(update={"position": (4, 2)})})
    with pytest.raises(ValueError, match="inside a wall"):
        build_world(cfg)


def test_rejects_out_of_bounds(small_config):
    cfg = small_config.model_copy(update={"start": (50, 0)})
    with pytest.raises(ValueError, match="outside"):
        build_world(cfg)


def test_generated_initial_signal_points_roughly_at_eve():
    for seed in range(5):
        world = build_world(MissionConfig(seed=seed))
        true = physics.bearing_deg(world.start, world.eve_position)
        assert abs(float(physics.angle_diff_deg(world.initial_signal.bearing_deg, true))) < 60
