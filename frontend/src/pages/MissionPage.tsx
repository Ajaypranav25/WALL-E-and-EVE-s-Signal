import { useCallback, useEffect, useMemo, useState } from "react";
import { GridMap, MapLegend, type Layers } from "../components/GridMap";
import { StepPanel } from "../components/StepPanel";
import { Timeline } from "../components/Timeline";
import { SAMPLE_RUNS } from "../lib/api";
import { outcomeTone } from "../lib/replay";
import { useRun } from "../lib/store";

const PLANNERS = [
  { id: "classical", label: "Classical (belief + utility)" },
  { id: "greedy", label: "Greedy baseline" },
  { id: "llm", label: "Claude strategist (server opt-in)" },
];

export default function MissionPage() {
  const { run, source, loading, error, apiOnline, loadSampleRun, runMission } = useRun();
  const [config, setConfig] = useState(SAMPLE_RUNS[0].name);
  const [planner, setPlanner] = useState("classical");
  const [seed, setSeed] = useState("");
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [layers, setLayers] = useState<Layers>({ belief: true, rays: true, truth: false });

  useEffect(() => {
    setStep(0);
    setPlaying(false);
  }, [run]);

  const marks = useMemo(() => run?.report.strategy_changes.map((c) => c.step) ?? [], [run]);
  const onPlaying = useCallback(
    (p: boolean) => {
      if (p && run && step >= run.steps.length - 1) setStep(0);
      setPlaying(p);
    },
    [run, step],
  );

  const seedValue = seed.trim() === "" ? undefined : Number(seed);
  const seedInvalid = seedValue !== undefined && (!Number.isInteger(seedValue) || seedValue < 0 || seedValue > 2147483647);

  const runLive = () => {
    if (seedInvalid) return;
    void runMission({ config_name: config === "random" ? undefined : config, seed: seedValue, planner });
  };

  const rec = run?.steps[Math.min(step, run.steps.length - 1)];

  return (
    <div className="mission-page">
      <section className="page-intro appear">
        <p className="eyebrow">Mission control</p>
        <h1>
          Watch WALL-E <em className="serif">reason</em> toward EVE.
        </h1>
        {run && (
          <p className="lede">
            {run.world.name}: {run.world.description || "a seeded wasteland."}{" "}
            <span className={`outcome ${outcomeTone(run.report.mission.outcome)}`}>{run.report.mission.outcome_text}</span> in {run.report.mission.steps} steps.
          </p>
        )}
      </section>

      <div className="mission-grid">
        <aside className="panel controls" aria-label="Mission controls">
          <h2>Mission</h2>
          <label className="field">
            <span>Config</span>
            <select value={config} onChange={(e) => setConfig(e.target.value)}>
              {SAMPLE_RUNS.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.title}
                </option>
              ))}
              <option value="random">Random world (seed)</option>
            </select>
          </label>
          <label className="field">
            <span>Planner</span>
            <select value={planner} onChange={(e) => setPlanner(e.target.value)}>
              {PLANNERS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Seed (optional)</span>
            <input inputMode="numeric" placeholder="config default" value={seed} onChange={(e) => setSeed(e.target.value)} aria-invalid={seedInvalid} />
            {seedInvalid && <small className="field-error">Use a whole number from 0 to 2147483647.</small>}
          </label>
          <div className="control-buttons">
            <button className="btn btn-solid" type="button" onClick={runLive} disabled={loading || apiOnline === false || seedInvalid}>
              {loading ? "Running…" : "Run mission"}
            </button>
            <button className="btn btn-ghost" type="button" disabled={loading || config === "random"} onClick={() => void loadSampleRun(config)}>
              Load recorded run
            </button>
          </div>
          <p className={`api-status ${apiOnline ? "on" : apiOnline === false ? "off" : ""}`}>
            <span aria-hidden="true" />
            {apiOnline === null ? "Checking the mission API…" : apiOnline ? "Mission API online" : "API offline: showing recorded runs. Start it with walle serve."}
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {source && <p className="muted small">Showing: {source}</p>}

          <h2>Layers</h2>
          <div className="toggles">
            {(
              [
                ["belief", "Belief heatmap"],
                ["rays", "Signal bearings"],
                ["truth", "Reveal ground truth"],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="toggle">
                <input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <MapLegend />
        </aside>

        <section className="map-col" aria-label="Mission map">
          {run && rec ? (
            <>
              <GridMap run={run} step={step} layers={layers} />
              <Timeline step={step} total={run.steps.length} tick={rec.tick} playing={playing} speed={speed} marks={marks} onStep={setStep} onPlaying={onPlaying} onSpeed={setSpeed} />
            </>
          ) : (
            <div className="map-empty">{loading ? "Loading mission…" : "No mission loaded."}</div>
          )}
        </section>

        {run && rec && <StepPanel run={run} rec={rec} onJump={(s) => { setPlaying(false); setStep(s); }} />}
      </div>
    </div>
  );
}
