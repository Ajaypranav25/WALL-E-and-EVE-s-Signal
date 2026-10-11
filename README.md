# WALL-E and EVE's Signal

An autonomous agent that explores a simulated wasteland, gathers clues and rations a limited battery to locate EVE, then decides WALL-E's next move.

- **Simulator** that loads a mission config and returns noisy observations for each action
- **Bayesian belief** over EVE's location *and* status, rebuilt from the evidence log when new knowledge changes how old evidence should be read
- **Classical planner** (belief per battery, triangulation, clue detours, return-to-charger guard rails), a **greedy baseline**, and an optional **Claude strategist**
- **Full action trace** (`trace.jsonl`): every action, observation, decision, reasoning and belief snapshot
- **Mission report** (`report.md` / `report.json`): evidence, inferred location/status, confidence, recommended next step
- **Visualizer**: a black, liquid-glass landing page plus a React mission-replay app (path, clues, decoys, belief heatmap, signal bearings, strategy changes), an ASCII map in the CLI, and a benchmark across random missions

```
backend/    Python package `signal_agent` (simulator, agent, CLI, FastAPI)
configs/    sample mission configs (YAML + JSON)
runs/       committed sample outputs: traces, reports, ASCII maps, benchmark
frontend/   Vite + React visualizer and the landing page
```

## Quick start

```bash
# backend (Python 3.11+)
cd backend
pip install -e ".[dev,llm]"
walle run ../configs/sample_mission.yaml --ascii        # writes runs/sample_mission/*
walle bench --n 100 --planners classical,greedy         # generalisation benchmark
walle validate ../configs/decoy_storm.json              # check a config
walle serve                                             # API on http://127.0.0.1:8000
python -m pytest --cov                                  # 98 tests, ~97% coverage

# frontend (Node 20+)
cd frontend
npm install
npm run dev        # http://localhost:5173 (landing) and /app.html (mission control); proxies /api to :8000
npm test
npm run build      # static site in frontend/dist
```

The visualizer works without the backend: it ships the recorded sample runs and benchmark (`npm run samples` copies them from `runs/`). With `walle serve` running, it can launch new missions and benchmarks live.

## Environment design

The world is a grid of **open ground**, **rubble** (costs 2.5x battery to enter) and **walls**. It is either surveyed in advance (`map.known: true`) or hidden under fog of war, in which case WALL-E sees terrain within `view_radius` and re-plans when it bumps into unseen walls.

**EVE** sits in one cell in one of three states, each with its own radio signature:

| Status | Beacon power (dBm at 1 cell) | Chance of pinging on a listen |
|---|---|---|
| active | -40 | 0.95 |
| dormant | -52 | 0.80 |
| damaged | -46 | 0.50 |

Received strength follows free-space path loss (`power - 20·log10(distance)`) plus Gaussian noise. Bearings carry Gaussian angular noise. Readings below the receiver sensitivity are not heard, so silence is evidence too.

**Decoys** are spoofing transmitters that replay EVE's beacon, usually louder than she is, and ping on every listen. The receiver cannot tell sources apart.

**Clues** can only be discovered by scanning near them and read by standing on them (`inspect`):

| Kind | What it tells WALL-E |
|---|---|
| `tracks` | a noisy bearing from the clue toward EVE |
| `log_fragment` | the compass sector (N, NE, ...) EVE headed from the clue |
| `scorch_mark` | a noisy distance from the clue to EVE |
| `plant` | a status hint (80% accurate) |

A configurable fraction of clues are **misleading** and describe a random location or status.

### Actions and costs (defaults)

| Action | Battery | Ticks | Effect |
|---|---|---|---|
| `move N/E/S/W` | 1.0 (rubble 2.5) | 1 | Bumping into a wall costs 0.25 and reveals it |
| `scan` | 2.0 | 2 | Detects EVE (90%), clues (85%) and decoys within `scan_radius` |
| `listen` | 1.0 | 1 | Bearing + strength for every source that pings |
| `inspect` | 0.5 | 1 | Reads the clue underfoot |
| `recharge` | +15 | 1 | Only at a charger |
| `end` | 0 | 0 | Ends the mission (at base: `returned_to_base`) |

A mission ends when EVE is sighted (`eve_located`), the battery runs dry (`stranded`), the time budget runs out (`time_exhausted`) or the agent ends it.

## Config format

Configs are YAML or JSON and validated with Pydantic (unknown keys are rejected). Anything omitted is generated deterministically from `seed`. See [`configs/`](configs/) for three complete examples, including a hand-drawn ASCII layout.

```yaml
name: Signal in the Dust
seed: 42
map: { width: 28, height: 20, wall_density: 0.12, rubble_density: 0.16, known: true }
# or map.layout: rows of '.', '#', '~'
start: [1, 18]
chargers: [[1, 18], [20, 3]]
eve: { position: [24, 6], status: dormant }        # optional; hidden from the agent
initial_signal:                                    # what WALL-E knows at launch
  bearing_deg: 62           # clockwise from north, from start
  strength_dbm: -82
  timestamp: -40            # ticks before launch; older readings are trusted less
  # or: coordinates: [20, 9], uncertainty: 7
resources: { battery_max: 90, battery_start: 90, time_limit: 350, reserve: 6 }
costs: { move: 1, rubble_move: 2.5, scan: 2, listen: 1, inspect: 0.5, recharge_rate: 15,
         time_move: 1, time_scan: 2, time_listen: 1, time_inspect: 1, time_recharge: 1 }
sensors: { scan_radius: 2, eve_detect_prob: 0.9, clue_detect_prob: 0.85, status_read_accuracy: 0.9,
           bearing_noise_deg: 14, strength_noise_db: 3.5, sensitivity_dbm: -92, view_radius: 2 }
clue_count: 6              # or clues: [{ kind: tracks, position: [8, 9], misleading: false }]
misleading_rate: 0.1
decoys: [{ position: [12, 4], power_dbm: -36 }]    # or decoy_count: 2
```

Coordinates are `[x, y]` with `x` growing east and `y` growing south.

## How the agent works

Each tick: **observe → update belief → decide → act → log**. The agent only ever sees the mission brief (map survey if any, chargers, start, initial signal, budgets, sensor specs) and observations; the `World` stays inside the environment.

**Belief.** `P[status, y, x]` over every cell and EVE status. Evidence is stored as a log and multiplied into the prior:

- *Listens* use probabilistic data association: at most one ping is EVE and the rest are clutter (known decoys plus a small rate of unknown spoofers). The chance EVE was heard at all depends on her status and on whether her beacon would clear the receiver from that cell, so hearing nothing pushes belief away from nearby cells.
- *Scans* that find nothing remove 90% of the mass within range; a sighting collapses location and updates status with the visual read's reliability.
- *Clues* add bearing, sector, ring-distance or status likelihoods, each with an outlier floor because clues can lie.
- When a scan uncovers a **decoy**, the posterior is rebuilt from the full evidence log with the decoy as a known source, so belief it had pulled away flows back toward EVE. Individual pings that fit the belief poorly are flagged in the trace as likely spoofed.

**Classical planner.** Guard rails first: if battery would not cover the trip to the nearest charger plus a reserve, head back and recharge to full; if time would not cover the trip home, turn back and end at base. Then, in order: inspect a clue underfoot, detour to a detected clue, re-listen once WALL-E has moved far enough for a new triangulation baseline, and otherwise drive to the cell with the most belief within scan range per unit of battery (Dijkstra over terrain costs, with a penalty for ending far from a charger), holding course unless a rival target is clearly better. Periodic sweep scans pick up clues along the way. Mode and goal changes are recorded as **strategy changes** with their reasons.

**Greedy baseline.** Listens every few steps, walks toward the loudest ping, scans periodically, keeps no belief. It shares the same safety guard rails so the comparison isolates the search strategy.

**Claude strategist (`--planner llm`).** At each decision point Claude receives a compact state summary built from WALL-E's memory (battery, time, ranked target cells with travel/return costs, pending clues, known decoys, recent evidence) and returns a structured directive (`goto_and_scan`, `listen`, `investigate_clue`, `recharge`, ...) via `messages.parse`. Classical code executes it. Safety checks always run first; infeasible, refused or failed directives fall back to the classical planner, and every override is logged. Calls are capped per mission (`SIGNAL_LLM_MAX_CALLS`, default 40). It uses `claude-opus-5-5` by default (`SIGNAL_LLM_MODEL` to change) and needs `ANTHROPIC_API_KEY`.

## Outputs

`walle run` writes to `runs/<config>/` (see the committed samples):

| File | Contents |
|---|---|
| `trace.jsonl` | One record per step: action, observation, decision (mode, goal, reasoning, alternatives considered), notes, state summary, top belief cells, belief snapshot, strategy change |
| `report.md`, `report.json` | Outcome, evidence found, inferred location and status with probabilities, confidence, recommended next step, strategy changes, and ground truth for evaluation |
| `map.txt` | ASCII map of the final state and path |
| `run.json` | Everything above in one bundle for the visualizer |

## Benchmark

`walle bench` runs every planner on the same seeded random missions (random size 22-32 x 16-22, terrain densities, bearing noise 10-22°, 3-7 clues with 5-20% misleading, 0-2 decoys, fog of war in ~30% of runs). Recorded result for 100 missions (`runs/benchmark.json`):

| Planner | EVE located | Stranded | Battery used when found | Ticks when found | Status correct | Decoy missions solved |
|---|---|---|---|---|---|---|
| classical | 100% | 0% | 76.4 | 75.4 | 100% | 61 / 61 |
| greedy | 43% | 1% | 115.4 | 117.9 | 82% | 12 / 61 |

The LLM planner can be added with `--planners classical,greedy,llm` (needs an API key; each mission makes up to `SIGNAL_LLM_MAX_CALLS` calls, so start with a small `--n`).

## API

`walle serve` exposes a small JSON API. Every response is `{"success", "data", "error"}`.

| Method | Path | Body |
|---|---|---|
| GET | `/api/health` | |
| GET | `/api/configs` | |
| GET | `/api/configs/{name}` | |
| POST | `/api/missions` | `{"config_name": "sample_mission", "planner": "classical", "seed": 3}` or an inline `"config"` |
| GET | `/api/runs/{id}` | last 20 runs are kept in memory |
| POST | `/api/benchmark` | `{"n": 20, "seed": 0, "planners": ["classical", "greedy"]}` (n ≤ 100) |

POST endpoints are rate limited per client and at most two missions/benchmarks run at once. Inline configs sent to the API are capped at 40x40 maps and `time_limit` 1000 (the CLI has no such cap). The Claude planner spends the server's API key, so it is off on the API unless `SIGNAL_API_ALLOW_LLM=1` is set. Config names are restricted to `[A-Za-z0-9_-]` and resolved inside `configs/` (override with `SIGNAL_CONFIG_DIR`).

## Landing page

`frontend/index.html` is a single file with inline CSS and a small script, built from the provided design spec and rebranded for this project. The hero background is living dust: one frame of the provided video (the CloudFront file, with an H.264 copy in `frontend/public/hero.mp4` because the original is HEVC 10-bit, which Chrome on most Windows and Linux machines cannot decode) seeds about 50k particles on a canvas. They drift through a slowly changing curl-noise field and never reform, so the dust keeps dispersing for as long as the page is open; the cursor parts it with a soft swirl and lights the grains around it. With reduced motion it renders a single still frame, and if the canvas or video pixels are unavailable it falls back to playing the video once. Inter and Instrument Serif are self-hosted under the SIL Open Font License.
