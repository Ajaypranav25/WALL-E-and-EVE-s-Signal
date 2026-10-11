import { useEffect, useState } from "react";
import { ApiError, api, loadSample } from "../lib/api";
import { useRun } from "../lib/store";
import type { BenchResult, BenchSummary } from "../types";

// Fixed planner -> hue mapping (validated dark categorical slots); never re-assigned by rank.
const PLANNER_COLOR: Record<string, string> = { classical: "#3987e5", greedy: "#d95926", llm: "#199e70" };
const PLANNER_LABEL: Record<string, string> = { classical: "Classical", greedy: "Greedy", llm: "Claude" };

interface Metric {
  key: keyof BenchSummary;
  label: string;
  format: (v: number) => string;
  max?: number;
  better: "higher" | "lower";
}

const METRICS: Metric[] = [
  { key: "success_rate", label: "EVE located", format: (v) => `${Math.round(v * 100)}%`, max: 1, better: "higher" },
  { key: "decoy_missions_solved", label: "Decoy missions solved", format: (v) => `${Math.round(v * 100)}%`, max: 1, better: "higher" },
  { key: "status_accuracy", label: "Status inferred correctly", format: (v) => `${Math.round(v * 100)}%`, max: 1, better: "higher" },
  { key: "mean_battery_when_found", label: "Battery used when found", format: (v) => v.toFixed(0), better: "lower" },
  { key: "mean_time_when_found", label: "Ticks to find EVE", format: (v) => v.toFixed(0), better: "lower" },
  { key: "mean_location_error", label: "Location error (cells)", format: (v) => v.toFixed(2), better: "lower" },
];

function MetricTile({ bench, metric }: { bench: BenchResult; metric: Metric }) {
  const values = bench.planners.map((p) => ({ planner: p, value: bench.results[p]?.summary[metric.key] as number | null }));
  const max = metric.max ?? Math.max(1, ...values.map((v) => v.value ?? 0));
  return (
    <figure className="metric-tile">
      <figcaption>
        {metric.label} <span className="muted">({metric.better} is better)</span>
      </figcaption>
      <div className="bars">
        {values.map(({ planner, value }) => (
          <div key={planner} className="bar-row" title={`${PLANNER_LABEL[planner] ?? planner}: ${value === null ? "n/a" : metric.format(value)}`}>
            <span className="bar-label">{PLANNER_LABEL[planner] ?? planner}</span>
            <div className="bar-track">
              {value !== null && <div className="bar" style={{ width: `${Math.max(1.5, (value / max) * 100)}%`, background: PLANNER_COLOR[planner] }} />}
            </div>
            <span className="bar-value">{value === null ? "n/a" : metric.format(value)}</span>
          </div>
        ))}
      </div>
    </figure>
  );
}

export default function BenchPage() {
  const { apiOnline } = useRun();
  const [bench, setBench] = useState<BenchResult | null>(null);
  const [label, setLabel] = useState("recorded");
  const [n, setN] = useState(20);
  const [seed, setSeed] = useState(0);
  const [planners, setPlanners] = useState<string[]>(["classical", "greedy"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [table, setTable] = useState(false);

  useEffect(() => {
    loadSample<BenchResult>("benchmark").then(setBench, (e: Error) => setError(e.message));
  }, []);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setBench(await api.benchmark({ n, seed, planners }));
      setLabel("live");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Benchmark failed.");
    } finally {
      setBusy(false);
    }
  };

  const togglePlanner = (p: string) => setPlanners((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));
  const nInvalid = !Number.isInteger(n) || n < 1 || n > 100;

  return (
    <div className="bench-page">
      <section className="page-intro appear">
        <p className="eyebrow">Generalisation benchmark</p>
        <h1>
          One agent, <em className="serif">many</em> wastelands.
        </h1>
        <p className="lede">
          Every mission is a fresh seeded world: random size, terrain, noise, clue count, misleading clues, up to two decoys and, in roughly a third of runs, fog of war. Same worlds for every planner.
        </p>
      </section>

      <div className="bench-controls panel">
        <label className="field inline">
          <span>Missions</span>
          <input type="number" min={1} max={100} value={n} onChange={(e) => setN(Number(e.target.value))} aria-invalid={nInvalid} />
        </label>
        <label className="field inline">
          <span>Start seed</span>
          <input type="number" min={0} value={seed} onChange={(e) => setSeed(Math.max(0, Number(e.target.value)))} />
        </label>
        <div className="planner-picks" role="group" aria-label="Planners">
          {["classical", "greedy", "llm"].map((p) => (
            <button key={p} type="button" className="pill pill-sm" aria-pressed={planners.includes(p)} onClick={() => togglePlanner(p)}>
              <i className="swatch" style={{ background: PLANNER_COLOR[p] }} />
              {PLANNER_LABEL[p]}
            </button>
          ))}
        </div>
        <button className="btn btn-solid" type="button" onClick={run} disabled={busy || !apiOnline || nInvalid || planners.length === 0}>
          {busy ? "Running…" : "Run benchmark"}
        </button>
        {!apiOnline && <p className="muted small">API offline: showing the recorded 100-mission run.</p>}
        {planners.includes("llm") && <p className="muted small">The Claude planner calls the API on every decision point; keep the mission count small.</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </div>

      {bench && (
        <>
          <div className="bench-head">
            <ul className="legend" aria-label="Planners">
              {bench.planners.map((p) => (
                <li key={p}>
                  <i className="swatch" style={{ background: PLANNER_COLOR[p] }} />
                  {PLANNER_LABEL[p] ?? p}
                </li>
              ))}
            </ul>
            <p className="muted small">
              {label === "live" ? "Live" : "Recorded"} run · {bench.n} missions from seed {bench.seed}
            </p>
            <button type="button" className="pill pill-sm" aria-pressed={table} onClick={() => setTable(!table)}>
              {table ? "Show charts" : "Show table"}
            </button>
          </div>
          {table ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Metric</th>
                    {bench.planners.map((p) => (
                      <th key={p} scope="col">{PLANNER_LABEL[p] ?? p}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((m) => (
                    <tr key={m.key}>
                      <th scope="row">{m.label}</th>
                      {bench.planners.map((p) => {
                        const v = bench.results[p]?.summary[m.key] as number | null;
                        return <td key={p}>{v === null || v === undefined ? "n/a" : m.format(v)}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="metric-grid">
              {METRICS.map((m) => (
                <MetricTile key={m.key} bench={bench} metric={m} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
