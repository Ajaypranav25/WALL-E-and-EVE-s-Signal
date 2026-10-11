import numpy as np
import pytest

from signal_agent import physics
from signal_agent.belief import Belief, Evidence
from signal_agent.config import InitialSignal, Sensors


def make_belief(w=20, h=15):
    return Belief(w, h, Sensors(), np.ones((h, w), dtype=bool))


def eve_ping(origin, eve, power=-40.0):
    return {"bearing_deg": physics.bearing_deg(origin, eve), "strength_dbm": float(physics.expected_strength(power, physics.distance(origin, eve)))}


def test_prior_is_normalised_and_uniform():
    b = make_belief()
    assert b.posterior.sum() == pytest.approx(1.0)
    assert b.location.max() == pytest.approx(b.location.min())


def test_triangulation_concentrates_on_source():
    b = make_belief()
    eve = (15, 4)
    for origin in [(2, 13), (10, 13), (2, 6)]:
        b.add(Evidence("pings", origin, {"pings": [eve_ping(origin, eve)]}, 0))
    (x, y), _ = b.map_estimate()
    assert physics.distance((x, y), eve) <= 2
    assert b.mass_within(eve, 2) > 0.3


def test_scan_miss_removes_mass():
    b = make_belief()
    before = b.mass_within((5, 5), 2)
    b.add(Evidence("scan_miss", (5, 5), {}, 0))
    assert b.mass_within((5, 5), 2) < before * 0.2


def test_eve_seen_collapses_location():
    b = make_belief()
    b.add(Evidence("eve_seen", (3, 3), {"position": (3, 3), "status": "damaged"}, 0))
    assert b.map_estimate()[0] == (3, 3)
    assert b.map_estimate()[1] == pytest.approx(1.0)
    assert max(b.status, key=b.status.get) == "damaged"


def test_decoy_reinterprets_past_pings():
    b = make_belief()
    eve, decoy = (16, 3), (4, 3)
    for origin in [(10, 13), (2, 13), (17, 13)]:
        pings = [eve_ping(origin, eve), eve_ping(origin, decoy, power=-38.0)]
        b.add(Evidence("pings", origin, {"pings": pings}, 0))
    eve_before, decoy_before = b.mass_within(eve, 2), b.mass_within(decoy, 2)
    assert b.add_decoy("decoy-1", decoy)
    assert not b.add_decoy("decoy-1", decoy)
    assert b.mass_within(decoy, 2) < decoy_before
    assert b.mass_within(eve, 2) > eve_before


def test_silence_pushes_belief_away():
    b = make_belief()
    b.add(Evidence("pings", (10, 7), {"pings": []}, 0))
    assert b.mass_within((10, 7), 3) < make_belief().mass_within((10, 7), 3)


@pytest.mark.parametrize("payload", [{"bearing_deg": 90.0}, {"sector": "east"}])
def test_directional_clues_shift_mass(payload):
    b = make_belief()
    b.add(Evidence("clue", (5, 7), payload, 0))
    assert b.location[:, 8:].sum() > b.location[:, :4].sum()


def test_distance_clue_builds_ring():
    b = make_belief()
    b.add(Evidence("clue", (10, 7), {"distance_estimate": 5.0}, 0))
    assert b.location[7, 15] > b.location[7, 10]


def test_status_hint_updates_status_only():
    b = make_belief()
    b.add(Evidence("clue", (5, 7), {"status_hint": "dormant"}, 0))
    assert max(b.status, key=b.status.get) == "dormant"
    assert b.location.max() == pytest.approx(b.location.min())


def test_initial_coordinates_prior():
    b = make_belief()
    b.add(Evidence("initial", (0, 14), {"signal": InitialSignal(coordinates=(12, 3), uncertainty=2)}, 0))
    assert physics.distance(b.map_estimate()[0], (12, 3)) <= 1


def test_initial_bearing_prior():
    b = make_belief()
    b.add(Evidence("initial", (0, 14), {"signal": InitialSignal(bearing_deg=45, strength_dbm=-60, timestamp=-30)}, 0))
    assert b.location[:7, 7:].sum() > b.location[:7, :3].sum()


def test_mark_wall_credible_region_and_summaries():
    b = make_belief()
    b.mark_wall((0, 0))
    assert b.location[0, 0] == 0
    assert 0 < len(b.credible_region(0.5)) < 20 * 15
    assert b.entropy_bits() > 0
    assert len(b.top_cells(3)) == 3


def test_contradictory_evidence_resets_to_prior():
    b = Belief(4, 4, Sensors(), np.ones((4, 4), dtype=bool))
    for x in range(4):
        for y in range(4):
            b.mark_wall((x, y)) if (x, y) != (3, 3) else None
    b.mark_wall((3, 3))
    assert np.isfinite(b.posterior).all()


def test_outlier_score_flags_inconsistent_ping():
    b = make_belief()
    eve = (15, 4)
    for origin in [(2, 13), (10, 13)]:
        b.add(Evidence("pings", origin, {"pings": [eve_ping(origin, eve)]}, 0))
    good = {"bearing_deg": physics.bearing_deg((2, 6), eve), "strength_dbm": -60.0}
    bad = {"bearing_deg": (physics.bearing_deg((2, 6), eve) + 180) % 360, "strength_dbm": -45.0}
    assert b.ping_outlier_score((2, 6), bad) > b.ping_outlier_score((2, 6), good)


def test_von_mises_handles_tight_noise():
    assert np.isfinite(physics.von_mises_pdf(0.0, 1.0))
    assert physics.von_mises_pdf(0.0, 10.0) > physics.von_mises_pdf(30.0, 10.0)
