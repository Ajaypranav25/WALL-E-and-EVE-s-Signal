const LOOP = [
  { title: "Observe", body: "The environment returns position, battery, time, terrain around WALL-E and anything the last action revealed." },
  { title: "Update belief", body: "A Bayesian grid over EVE's cell and status folds in pings, scans, clues and sightings." },
  { title: "Decide", body: "Guard rails first (battery, time), then read clues, re-listen for a new baseline, or drive to the best-value cell." },
  { title: "Act & log", body: "One action per tick. Action, observation, decision, reasoning and a belief snapshot go to the trace." },
];

const ACTIONS = [
  ["move N/E/S/W", "1.0 (rubble 2.5)", "1", "Walls block; bumping costs a little and reveals the wall."],
  ["scan", "2.0", "2", "Finds EVE, clues and decoys within the scan radius. Can miss (90% / 85%)."],
  ["listen", "1.0", "1", "Noisy bearing + strength for every source that pings. Decoys ping too."],
  ["inspect", "0.5", "1", "Reads a clue WALL-E is standing on."],
  ["recharge", "+15 battery", "1", "Only at a charger."],
  ["end", "0", "0", "Ends the mission and writes the report."],
];

const CONFIG = `name: Signal in the Dust
seed: 42                      # everything omitted is generated from this
map: { width: 28, height: 20, wall_density: 0.12, rubble_density: 0.16, known: true }
start: [1, 18]
chargers: [[1, 18], [20, 3]]
eve: { position: [24, 6], status: dormant }       # optional; hidden from the agent
initial_signal: { bearing_deg: 62, strength_dbm: -82, timestamp: -40 }
#   or: { coordinates: [20, 9], uncertainty: 7, timestamp: -120 }
resources: { battery_max: 90, time_limit: 350, reserve: 6 }
costs: { move: 1, rubble_move: 2.5, scan: 2, listen: 1, inspect: 0.5, recharge_rate: 15 }
sensors: { scan_radius: 2, bearing_noise_deg: 14, strength_noise_db: 3.5 }
clue_count: 6                 # or an explicit clues: [{ kind, position, misleading }]
misleading_rate: 0.1
decoys: [{ position: [12, 4], power_dbm: -36 }]   # or decoy_count: 2`;

const RUN = `# backend
cd backend
pip install -e ".[dev,llm]"
walle run configs/sample_mission.yaml --out ../runs/sample_mission --ascii
walle bench --n 100 --planners classical,greedy       # generalisation benchmark
walle serve                                           # API on :8000
SIGNAL_API_ALLOW_LLM=1 walle serve                    # also allow the Claude planner

# frontend
cd frontend && npm install && npm run dev             # http://localhost:5173`;

export default function HowPage() {
  return (
    <article className="how-page">
      <section className="page-intro appear">
        <p className="eyebrow">How it works</p>
        <h1>
          A search that <em className="serif">thinks</em> in probabilities.
        </h1>
        <p className="lede">
          WALL-E never sees the world directly. It starts with a stale radio reading and a battery budget, and learns where EVE is only by acting: listening, scanning, reading clues and walking.
        </p>
      </section>

      <ol className="loop">
        {LOOP.map((s, i) => (
          <li key={s.title} className="panel appear" style={{ ["--d" as string]: `${0.08 * i}s` }}>
            <span className="loop-num">0{i + 1}</span>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
          </li>
        ))}
      </ol>

      <div className="how-grid">
        <section className="panel">
          <h2>The environment</h2>
          <p>
            A grid of open ground, rubble (costs more battery) and walls, either surveyed in advance or hidden under fog of war. EVE sits in one cell in one of three states: <strong>active</strong> (loud, reliable beacon), <strong>dormant</strong> (12 dB quieter) or <strong>damaged</strong> (pings only half the time).
          </p>
          <p>
            Signal strength falls off with distance (free-space path loss) and every reading carries Gaussian noise. <strong>Decoy</strong> transmitters replay EVE's beacon, often louder than she is. Clues come in four kinds: hover-tracks (a bearing), log fragments (a compass sector), scorch marks (a distance) and plants (a status hint), and some of them are deliberately wrong.
          </p>
        </section>

        <section className="panel">
          <h2>Belief</h2>
          <p>
            The agent keeps <span className="mono">P(cell, status)</span> for every cell. Each listen is scored with probabilistic data association: at most one ping is EVE, the rest are clutter, and hearing nothing is evidence too. A scan that finds nothing removes 90% of the mass within range.
          </p>
          <p>
            Evidence is stored, not just multiplied in. When a scan uncovers a decoy, every past listen is <strong>re-read</strong> with that decoy as a known source, and belief that was pulled toward it flows back to EVE.
          </p>
        </section>

        <section className="panel">
          <h2>Planning</h2>
          <p>
            Each tick the classical planner checks battery against the cost to the nearest charger plus a reserve, and time against the trip home. Then it reads a nearby clue, re-listens once it has moved far enough for a new triangulation baseline, or drives toward the cell with the most belief within scan range per unit of battery, holding course unless a rival target is clearly better.
          </p>
          <p>
            The <strong>Claude strategist</strong> picks the next sub-goal from the same summary through structured output, and classical code executes it. Safety checks always run first and infeasible directives fall back to classical. Each override is logged.
          </p>
        </section>

        <section className="panel">
          <h2>Actions and costs</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Action</th>
                  <th scope="col">Battery</th>
                  <th scope="col">Ticks</th>
                  <th scope="col">Notes</th>
                </tr>
              </thead>
              <tbody>
                {ACTIONS.map(([a, b, t, n]) => (
                  <tr key={a}>
                    <th scope="row" className="mono">{a}</th>
                    <td>{b}</td>
                    <td>{t}</td>
                    <td>{n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div className="how-grid two">
        <section className="panel">
          <h2>Mission config (YAML or JSON)</h2>
          <pre className="code">{CONFIG}</pre>
        </section>
        <section className="panel">
          <h2>Run it</h2>
          <pre className="code">{RUN}</pre>
          <p className="muted small">
            The Claude planner needs <span className="mono">ANTHROPIC_API_KEY</span> and defaults to <span className="mono">claude-opus-5-5</span>; set <span className="mono">SIGNAL_LLM_MODEL</span> to change it.
          </p>
        </section>
      </div>
    </article>
  );
}
