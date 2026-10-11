"""Bayesian belief over EVE's location and status.

The posterior is a grid ``P[status, y, x]``. Rather than folding evidence in
once and forgetting it, every observation is kept as an Evidence record and
the posterior is ``prior x product of likelihoods``. When WALL-E later learns
something that changes how old evidence should be read (most importantly:
a signal source turns out to be a decoy), the posterior is rebuilt from the
full log so earlier pings are re-attributed to the decoy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import physics
from .config import STATUSES, InitialSignal, Sensors
from .world import STATUS_PRIOR, WALL

COMPASS_CENTRES = {
    "north": 0.0, "north-east": 45.0, "east": 90.0, "south-east": 135.0,
    "south": 180.0, "south-west": 225.0, "west": 270.0, "north-west": 315.0,
}
UNKNOWN_CLUTTER_RATE = 0.4   # expected pings per listen from sources WALL-E has not identified
CLUE_OUTLIER_RATE = 0.15     # chance any single clue is junk
TRACK_NOISE_DEG = 18.0
STATUS_HINT_ACCURACY = 0.8
PRIOR_FLOOR = 1e-12


@dataclass(frozen=True)
class Evidence:
    kind: str  # "pings" | "initial" | "scan_miss" | "clue" | "eve_seen"
    origin: tuple[int, int]
    data: dict[str, Any]
    tick: int


@dataclass
class Belief:
    width: int
    height: int
    sensors: Sensors
    passable: np.ndarray  # (h, w) bool, cells where EVE could physically be
    evidence: list[Evidence] = field(default_factory=list)
    known_decoys: dict[str, tuple[int, int]] = field(default_factory=dict)
    posterior: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        ys, xs = np.mgrid[: self.height, : self.width]
        self._xs = xs.astype(float)
        self._ys = ys.astype(float)
        self._status_prior = np.array(STATUS_PRIOR)[:, None, None]
        self.posterior = self._prior()

    # ------------------------------------------------------------ summaries
    @property
    def location(self) -> np.ndarray:
        """Marginal P(EVE at cell), shape (h, w)."""
        return self.posterior.sum(axis=0)

    @property
    def status(self) -> dict[str, float]:
        marg = self.posterior.sum(axis=(1, 2))
        return {s: float(p) for s, p in zip(STATUSES, marg)}

    def map_estimate(self) -> tuple[tuple[int, int], float]:
        loc = self.location
        idx = int(np.argmax(loc))
        y, x = divmod(idx, self.width)
        return (x, y), float(loc[y, x])

    def entropy_bits(self) -> float:
        p = self.location.ravel()
        p = p[p > 0]
        return float(-(p * np.log2(p)).sum())

    def credible_region(self, mass: float = 0.9) -> list[tuple[int, int]]:
        loc = self.location.ravel()
        order = np.argsort(loc)[::-1]
        cum = np.cumsum(loc[order])
        k = int(np.searchsorted(cum, mass)) + 1
        return [(int(i % self.width), int(i // self.width)) for i in order[:k]]

    def mass_within(self, centre: tuple[int, int], radius: float) -> float:
        d2 = (self._xs - centre[0]) ** 2 + (self._ys - centre[1]) ** 2
        return float(self.location[d2 <= radius * radius + 1e-9].sum())

    def top_cells(self, k: int = 5) -> list[dict[str, Any]]:
        loc = self.location.ravel()
        order = np.argsort(loc)[::-1][:k]
        return [{"cell": [int(i % self.width), int(i // self.width)], "p": round(float(loc[i]), 4)} for i in order]

    # ------------------------------------------------------------- updates
    def mark_wall(self, cell: tuple[int, int]) -> None:
        if self.passable[cell[1], cell[0]]:
            self.passable[cell[1], cell[0]] = False
            self.posterior[:, cell[1], cell[0]] = 0.0
            self._normalise()

    def add(self, ev: Evidence) -> None:
        self.evidence.append(ev)
        self.posterior = self.posterior * self._likelihood(ev)
        self._normalise()

    def add_decoy(self, decoy_id: str, position: tuple[int, int]) -> bool:
        """Register a confirmed decoy and re-read every past ping. Returns True if it was new."""
        if decoy_id in self.known_decoys:
            return False
        self.known_decoys[decoy_id] = position
        self.rebuild()
        return True

    def rebuild(self) -> None:
        post = self._prior()
        for ev in self.evidence:
            post = post * self._likelihood(ev)
            total = post.sum()
            post = post / total if total > 0 else self._prior()
        self.posterior = post

    def ping_outlier_score(self, origin: tuple[int, int], ping: dict[str, float]) -> float:
        """How poorly a single ping fits the current belief (higher = more suspicious)."""
        dist = np.hypot(self._xs - origin[0], self._ys - origin[1])
        g = self._eve_ping_density(dist, origin, ping)  # (3, h, w)
        fit = float((g * self.posterior).sum())
        clutter = self._clutter_density(origin, ping)
        return clutter / (fit + clutter + 1e-300)

    # ---------------------------------------------------------- internals
    def _prior(self) -> np.ndarray:
        base = self.passable.astype(float)
        base /= max(base.sum(), 1.0)
        return np.maximum(base[None, :, :] * self._status_prior, 0.0)

    def _normalise(self) -> None:
        total = self.posterior.sum()
        if total <= 0 or not math.isfinite(total):
            # Evidence contradicted itself completely: fall back to the prior rather than divide by zero.
            self.posterior = self._prior()
            return
        self.posterior /= total

    def _bearing_grid(self, origin: tuple[int, int]) -> np.ndarray:
        dx = self._xs - origin[0]
        dy = self._ys - origin[1]
        return np.degrees(np.arctan2(dx, -dy)) % 360.0

    def _eve_ping_density(self, dist: np.ndarray, origin: tuple[int, int], ping: dict[str, float], bearing_sigma: float | None = None) -> np.ndarray:
        sigma_b = bearing_sigma or self.sensors.bearing_noise_deg
        bearing = self._bearing_grid(origin)
        g_b = physics.von_mises_pdf(physics.angle_diff_deg(ping["bearing_deg"], bearing), sigma_b)
        g_b = np.where(dist < 0.5, 1.0 / (2 * math.pi), g_b)
        if ping.get("strength_dbm") is None:
            # Strength unknown: use the same flat strength density the clutter model uses.
            return np.broadcast_to(g_b / physics.STRENGTH_RANGE_DB, (3, *g_b.shape))
        out = np.empty((3, *dist.shape))
        for i, s in enumerate(STATUSES):
            mean = physics.expected_strength(physics.EVE_POWER_DBM[s], dist)
            out[i] = g_b * physics.normal_pdf(ping["strength_dbm"], mean, self.sensors.strength_noise_db)
        return out

    def _clutter_density(self, origin: tuple[int, int], ping: dict[str, float]) -> float:
        """Expected-count-weighted density of a ping coming from something other than EVE."""
        uniform = 1.0 / (2 * math.pi) / physics.STRENGTH_RANGE_DB
        total = UNKNOWN_CLUTTER_RATE * uniform
        for pos in self.known_decoys.values():
            diff = physics.angle_diff_deg(ping["bearing_deg"], physics.bearing_deg(origin, pos))
            total += float(physics.von_mises_pdf(diff, self.sensors.bearing_noise_deg)) / physics.STRENGTH_RANGE_DB
        return total

    def _likelihood(self, ev: Evidence) -> np.ndarray:
        handler = {
            "pings": self._lik_pings,
            "initial": self._lik_initial,
            "scan_miss": self._lik_scan_miss,
            "clue": self._lik_clue,
            "eve_seen": self._lik_eve_seen,
        }[ev.kind]
        return handler(ev)

    def _lik_pings(self, ev: Evidence) -> np.ndarray:
        """Probabilistic data association: at most one ping came from EVE, the rest are clutter.

        L(x, s) is proportional to (1 - d) + d * sum_j g(z_j | x, s) / clutter(z_j),
        with d the chance EVE was heard at all (emit probability x chance of
        clearing the receiver's sensitivity from cell x).
        """
        origin = ev.origin
        dist = np.hypot(self._xs - origin[0], self._ys - origin[1])
        detect = np.empty((3, self.height, self.width))
        emit = np.array([physics.EVE_EMIT_PROB[s] for s in STATUSES])[:, None, None]
        for i, s in enumerate(STATUSES):
            mean = physics.expected_strength(physics.EVE_POWER_DBM[s], dist)
            audible = physics.normal_cdf((mean - self.sensors.sensitivity_dbm) / self.sensors.strength_noise_db)
            detect[i] = physics.EVE_EMIT_PROB[s] * audible
        ratio = np.zeros((3, self.height, self.width))
        for ping in ev.data["pings"]:
            ratio += self._eve_ping_density(dist, origin, ping) / self._clutter_density(origin, ping)
        # A heard ping already lies above the threshold, so its density is emit x g;
        # audibility only enters through the chance of hearing nothing from EVE.
        return (1.0 - detect) + emit * ratio

    def _lik_initial(self, ev: Evidence) -> np.ndarray:
        sig: InitialSignal = ev.data["signal"]
        if sig.coordinates is not None:
            cx, cy = sig.coordinates
            d2 = (self._xs - cx) ** 2 + (self._ys - cy) ** 2
            spread = sig.uncertainty * (1.0 + abs(sig.timestamp) / 200.0)
            lik = np.exp(-0.5 * d2 / spread**2) + 0.02
            return np.broadcast_to(lik, (3, self.height, self.width)).copy()
        # Older readings are trusted less: widen the bearing error with age.
        sigma = self.sensors.bearing_noise_deg * (1.0 + abs(sig.timestamp) / 100.0)
        ping = {"bearing_deg": sig.bearing_deg, "strength_dbm": sig.strength_dbm}
        dist = np.hypot(self._xs - ev.origin[0], self._ys - ev.origin[1])
        g = self._eve_ping_density(dist, ev.origin, ping, bearing_sigma=sigma)
        # The briefing reading might itself have been spoofed, so keep a clutter floor.
        return g / self._clutter_density(ev.origin, ping) + 1.0

    def _lik_scan_miss(self, ev: Evidence) -> np.ndarray:
        r = self.sensors.scan_radius
        d2 = (self._xs - ev.origin[0]) ** 2 + (self._ys - ev.origin[1]) ** 2
        lik = np.where(d2 <= r * r + 1e-9, 1.0 - self.sensors.eve_detect_prob, 1.0)
        return np.broadcast_to(lik, (3, self.height, self.width)).copy()

    def _lik_eve_seen(self, ev: Evidence) -> np.ndarray:
        x, y = ev.data["position"]
        lik = np.zeros((3, self.height, self.width))
        acc = self.sensors.status_read_accuracy
        for i, s in enumerate(STATUSES):
            lik[i, y, x] = acc if s == ev.data["status"] else (1 - acc) / 2
        return lik

    def _lik_clue(self, ev: Evidence) -> np.ndarray:
        c = ev.data
        origin = ev.origin
        eps = CLUE_OUTLIER_RATE
        if "bearing_deg" in c:
            bearing = self._bearing_grid(origin)
            g = physics.von_mises_pdf(physics.angle_diff_deg(c["bearing_deg"], bearing), TRACK_NOISE_DEG) * 2 * math.pi
            lik = (1 - eps) * g + eps
        elif "sector" in c:
            diff = np.abs(physics.angle_diff_deg(self._bearing_grid(origin), COMPASS_CENTRES[c["sector"]]))
            lik = np.where(diff <= 32.5, 1.0, eps)
        elif "distance_estimate" in c:
            dist = np.hypot(self._xs - origin[0], self._ys - origin[1])
            est = c["distance_estimate"]
            sigma = 0.2 * est + 1.5
            lik = (1 - eps) * np.exp(-0.5 * ((dist - est) / sigma) ** 2) + eps
        elif "status_hint" in c:
            lik3 = np.array([STATUS_HINT_ACCURACY if s == c["status_hint"] else (1 - STATUS_HINT_ACCURACY) / 2 for s in STATUSES])
            return np.broadcast_to(lik3[:, None, None], (3, self.height, self.width)).copy()
        else:
            return np.ones((3, self.height, self.width))
        return np.broadcast_to(lik, (3, self.height, self.width)).copy()



def initial_passable(grid: np.ndarray, known: bool) -> np.ndarray:
    """Cells EVE could occupy as far as WALL-E knows at mission start."""
    if known:
        return grid != WALL
    return np.ones(grid.shape, dtype=bool)
