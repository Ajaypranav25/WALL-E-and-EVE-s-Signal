import numpy as np

from signal_agent.config import Costs
from signal_agent.navigation import KnownMap, dijkstra, direction_to, disk_sum
from signal_agent.world import OPEN, RUBBLE, UNKNOWN, WALL


def test_dijkstra_routes_around_walls_and_rubble():
    grid = np.full((3, 5), OPEN, dtype=np.int8)
    grid[1, 1:4] = WALL
    grid[0, 2] = RUBBLE
    km = KnownMap(grid)
    field = dijkstra(km.entry_costs(Costs()), [(0, 1)])
    path = field.path((4, 1))
    assert path[-1] == (4, 1)
    assert all(grid[y, x] != WALL for x, y in path)
    # The top row has rubble (2.5 to cross); the clear bottom row is cheaper.
    assert (2, 2) in path


def test_reverse_field_measures_cost_to_sources():
    km = KnownMap(np.full((1, 4), OPEN, dtype=np.int8))
    field = dijkstra(km.entry_costs(Costs()), [(0, 0)], reverse=True)
    assert field.cost[0, 3] == 3
    assert field.path((3, 0)) == [(2, 0), (1, 0), (0, 0)]


def test_unreachable_target_has_no_path():
    grid = np.full((3, 3), OPEN, dtype=np.int8)
    grid[:, 1] = WALL
    field = dijkstra(KnownMap(grid).entry_costs(Costs()), [(0, 0)])
    assert field.path((2, 2)) == []


def test_fog_map_updates_and_reports_new_walls():
    km = KnownMap.from_world_grid(np.zeros((4, 4), dtype=np.int8), known=False)
    assert (km.grid == UNKNOWN).all()
    assert km.update([(1, 1, WALL), (0, 0, OPEN)]) == [(1, 1)]
    assert km.version == 1
    assert km.update([(1, 1, WALL)]) == [] and km.version == 1


def test_entry_costs_cached_per_version():
    km = KnownMap(np.zeros((2, 2), dtype=np.int8))
    first = km.entry_costs(Costs())
    assert km.entry_costs(Costs()) is first
    km.update([(0, 0, WALL)])
    assert km.entry_costs(Costs()) is not first


def test_disk_sum_and_direction():
    field = np.zeros((5, 5))
    field[2, 2] = 1.0
    assert disk_sum(field, 1)[2, 3] == 1.0 and disk_sum(field, 1)[0, 0] == 0.0
    assert direction_to((1, 1), (1, 0)) == "N" and direction_to((1, 1), (0, 1)) == "W"
