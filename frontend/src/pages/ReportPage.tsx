import { useState } from "react";
import { outcomeTone, pct } from "../lib/replay";
import { useRun } from "../lib/store";
import type { RunBundle } from "../types";

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <span className="tile-label">{label}</span>
      <strong className="tile-value">{value}</strong>
      {sub && <span className="tile-sub">{sub}</span>}
    </div>
  );
}

export default function ReportPage() {
  const { run, loading } = useRun();
  const [showTruth, setShowTruth] = useState(false);
  if (!run) return <div className="page-intro">{loading ? "Loading report…" : "Load a mission first."}</div>;
  return <Report run={run} showTruth={showTruth} onTruth={setShowTruth} />;
}

function Report({ run, showTruth, onTruth }: { run: RunBundle; showTruth: boolean; onTruth: (v: boolean) => void }) {
  const { mission: m, evidence: ev, inference: inf, ground_truth: gt } = run.report;
  const slug = m.name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const sig = ev.initial_signal;

  return (
    <article className="report-page">
      <section className="page-intro appear">
        <p className="eyebrow">Mission report · {m.planner} planner · seed {m.seed}</p>
        <h1>
          {m.name}: <em className="serif">{m.outcome_text}</em>
        </h1>
        <div className="report-actions">
          <button className="btn btn-ghost" type="button" onClick={() => download(`${slug}-report.json`, JSON.stringify(run.report, null, 2), "application/json")}>
            Download report.json
          </button>
          <button className="btn btn-ghost" type="button" onClick={() => download(`${slug}-trace.jsonl`, run.steps.map((s) => JSON.stringify(s)).join("\n"), "application/x-ndjson")}>
            Download trace.jsonl
          </button>
          <a className="btn btn-solid" href="#/mission">
            Replay mission
          </a>
        </div>
      </section>

      <div className="tiles">
        <Tile label="Outcome" value={m.outcome_text} sub={`${m.steps} steps`} />
        <Tile label="Inferred location" value={`(${inf.location[0]}, ${inf.location[1]})`} sub={`90% region: ${inf.credible_region_90_cells} cell${inf.credible_region_90_cells === 1 ? "" : "s"}`} />
        <Tile label="Inferred status" value={inf.status} sub={Object.entries(inf.status_probabilities).map(([k, v]) => `${k} ${pct(v)}`).join(" · ")} />
        <Tile label="Confidence" value={pct(inf.confidence)} sub={inf.confidence_text} />
        <Tile label="Battery" value={`${m.battery_used} used`} sub={`${m.battery_left} left · ${m.recharges} recharge ticks`} />
        <Tile label="Time" value={`${m.time_used} / ${m.time_limit}`} sub={`${m.distance_travelled} cells driven`} />
      </div>

      <section className={`next-step ${outcomeTone(m.outcome)}`}>
        <h2>Recommended next step</h2>
        <p>{run.report.recommended_next_step}</p>
      </section>

      <div className="report-columns">
        <section className="panel">
          <h2>Evidence found</h2>
          <ul className="evidence">
            <li>
              <span className="ev-kind">Briefing signal</span>
              {sig.bearing_deg !== null ? `bearing ${sig.bearing_deg}°` : `near (${sig.coordinates?.join(", ")}) ±${sig.uncertainty}`}
              {sig.strength_dbm !== null && `, ${sig.strength_dbm} dBm`}, received {Math.abs(sig.timestamp)} ticks before launch
            </li>
            <li>
              <span className="ev-kind">Radio</span>
              {ev.listens} listens, {ev.pings_heard} pings heard, {ev.suspicious_pings} flagged as likely spoofed
            </li>
            {ev.clues_read.map((c) => (
              <li key={c.id}>
                <span className="ev-kind">
                  {c.id} · {c.kind.replace("_", " ")}
                </span>
                ({c.position.join(", ")}) {c.message}
              </li>
            ))}
            {ev.clues_detected_unread.map((c) => (
              <li key={c.id}>
                <span className="ev-kind">{c.id}</span>detected at ({c.position.join(", ")}) but not read
              </li>
            ))}
            {ev.decoys_identified.map((d) => (
              <li key={d.id}>
                <span className="ev-kind decoy">{d.id}</span>spoofing transmitter identified at ({d.position.join(", ")}); past pings re-read
              </li>
            ))}
            {ev.eve_sighting && (
              <li>
                <span className="ev-kind eve">EVE sighted</span>at ({ev.eve_sighting.position.join(", ")}), visual status read: {ev.eve_sighting.status}
                {ev.eve_sighting.status !== inf.status && ` (outvoted by the signal history, which favours ${inf.status})`}
              </li>
            )}
          </ul>
        </section>

        <section className="panel">
          <h2>Strategy changes</h2>
          {run.report.strategy_changes.length === 0 ? (
            <p className="muted">None.</p>
          ) : (
            <ol className="timeline-list">
              {run.report.strategy_changes.map((c) => (
                <li key={c.step}>
                  <span className="mono">step {c.step}</span>
                  <div>
                    <strong>
                      {c.from} → {c.to}
                    </strong>
                    <p>{c.reason}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section className="panel truth">
        <div className="truth-head">
          <h2>Ground truth</h2>
          <label className="toggle">
            <input type="checkbox" checked={showTruth} onChange={(e) => onTruth(e.target.checked)} />
            <span>Reveal (evaluation only, never visible to the agent)</span>
          </label>
        </div>
        {showTruth && (
          <ul className="evidence">
            <li>
              <span className="ev-kind eve">EVE</span>({gt.eve_position.join(", ")}), {gt.eve_status}. Location error {gt.location_error_cells} cells; status {gt.status_correct ? "correct" : "wrong"}.
            </li>
            <li>
              <span className="ev-kind decoy">Decoys</span>
              {gt.decoys.length ? gt.decoys.map((d) => `(${d.position.join(", ")})`).join(", ") : "none"}
            </li>
            <li>
              <span className="ev-kind">Clues</span>
              {gt.clues.map((c) => `${c.id} ${c.kind}${c.misleading ? " (misleading)" : ""}`).join(", ")}
            </li>
          </ul>
        )}
      </section>
    </article>
  );
}
