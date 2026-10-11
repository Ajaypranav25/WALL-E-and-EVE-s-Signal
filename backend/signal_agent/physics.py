"""Signal propagation model shared by the environment (truth) and the agent (inference).

Coordinates are (x, y) with x growing east and y growing south; bearings are
degrees clockwise from north. The agent knows this sensor model but never the
true source positions.
"""

from __future__ import annotations

import math

import numpy as np

from .config import EveStatus

# Transmit power (dBm at 1 cell) and chance a source pings on a given listen.
EVE_POWER_DBM: dict[EveStatus, float] = {"active": -40.0, "dormant": -52.0, "damaged": -46.0}
EVE_EMIT_PROB: dict[EveStatus, float] = {"active": 0.95, "dormant": 0.8, "damaged": 0.5}
DECOY_EMIT_PROB = 1.0
PATH_LOSS_EXPONENT = 2.0
STRENGTH_RANGE_DB = 70.0  # width of the uniform clutter strength density


def bearing_deg(frm: tuple[int, int], to: tuple[int, int]) -> float:
    dx = to[0] - frm[0]
    dy = to[1] - frm[1]
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def expected_strength(power_dbm: float, dist: float | np.ndarray) -> float | np.ndarray:
    return power_dbm - 10.0 * PATH_LOSS_EXPONENT * np.log10(np.maximum(dist, 1.0))


def angle_diff_deg(a: float | np.ndarray, b: float | np.ndarray) -> float | np.ndarray:
    """Smallest signed difference a - b in degrees, in [-180, 180)."""
    return (np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0


def von_mises_pdf(diff_deg: float | np.ndarray, sigma_deg: float) -> np.ndarray:
    """Von Mises density over radians for an angular error given in degrees."""
    kappa = 1.0 / math.radians(sigma_deg) ** 2
    diff = np.radians(np.asarray(diff_deg, dtype=float))
    # Scaled Bessel i0e(k) = exp(-k) * I0(k); use its asymptote for large k.
    i0e = float(np.i0(kappa)) * math.exp(-kappa) if kappa < 500 else 1.0 / math.sqrt(2 * math.pi * kappa)
    return np.exp(kappa * (np.cos(diff) - 1.0)) / (2.0 * math.pi * i0e)


def normal_pdf(x: float | np.ndarray, mean: float | np.ndarray, sigma: float) -> np.ndarray:
    z = (np.asarray(x) - np.asarray(mean)) / sigma
    return np.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def normal_cdf(x: float | np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))
