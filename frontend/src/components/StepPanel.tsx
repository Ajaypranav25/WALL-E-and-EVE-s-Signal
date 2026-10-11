import { pct } from "../lib/replay";
import type { EveStatus, RunBundle, StepRecord } from "../types";

const ACTION_LABEL: Record<string, string> = {
  move: "Move",
  scan: "Scan",
  listen: "Listen",
  inspect: "Inspect clue",
  recharge: "Recharge",
  end: "End mission",
};
const DIRECTION: Record<string, string> = { N: "north", E: "east", S: "south", W: "west" };
const STATUSES: EveStatus[] = ["active", "dormant", "damaged"];

function Meter({ label, value, max, unit = "" }: { label: string; value: number; max: number; unit?: string }) {
  const ratio = Math.max(0, Math.min(1, value / max));
  const tone = ratio < 0.2 ? "bad" : ratio < 0.4 ? "warn" : "ok";
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span className="meter-value">
          {value.toFixed(0)}
          {unit} / {max}
          {unit}
        </span>
      </div>
      <div className="meter-track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.round(value)}>
        <div className={`meter-fill ${tone}`} style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}

export function StepPanel({ run, rec, onJump }: { run: RunBundle; rec: StepRecord; onJump: (step: number) => void }) {
  const { world } = run;
  const action = rec.action ? `${ACTION_LABEL[rec.action.kind]}${rec.action.direction ? ` ${DIRECTION[rec.action.direction]}` : ""}` : "Mission start";
  const timeLeft = world.time_limit - rec.observation.time_used;
  const changes = run.report.strategy_changes;

  return (
    <aside className="panel step-panel" aria-live="polite">
      <div className="step-head">
        <span className="badge">{action}</span>
        <span className={`chip mode-${rec.decision.mode}`}>{rec.decision.mode}</span>
        {rec.decision.source !== "classical" && rec.decision.source !== "brief" && <span className="chip">{rec.decision.source}</span>}
      </div>
      <p className="reasoning">{rec.decision.reasoning}</p>
      {rec.notes.length > 0 && (
        <ul className="notes">
          {rec.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      {rec.observation.pings && rec.observation.pings.length > 0 && (
        <p className="obs-line">
          Pings:{" "}
          {rec.observation.pings.map((p, i) => (
            <span key={i} className="mono">
              {p.bearing_deg.toFixed(0)}° / {p.strength_dbm.toFixed(0)} dBm{i < rec.observation.pings!.length - 1 ? ", " : ""}
            </span>
          ))}
        </p>
      )}
      <p className="obs-line muted">Result: {rec.observation.result}</p>

      <div className="meters">
        <Meter label="Battery" value={rec.observation.battery} max={world.battery_max} />
        <Meter label="Time left" value={timeLeft} max={world.time_limit} />
      </div>

      <section className="belief-block" aria-label="Belief summary">
        <h3>Belief</h3>
        <p className="kv">
          <span>Best estimate</span>
          <strong>
            ({rec.state.map_estimate[0]}, {rec.state.map_estimate[1]}) · {pct(rec.state.map_p, 1)}
          </strong>
        </p>
        <p className="kv">
          <span>Uncertainty</span>
          <strong>{rec.state.entropy_bits.toFixed(2)} bits</strong>
        </p>
        <div className="status-bars">
          {STATUSES.map((s) => (
            <div key={s} className="status-row">
              <span>{s}</span>
              <div className="status-track">
                <div className="status-fill" style={{ width: pct(rec.state.status[s]) }} />
              </div>
              <span className="mono">{pct(rec.state.status[s])}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="changes" aria-label="Strategy changes">
        <h3>Strategy changes</h3>
        {changes.length === 0 && <p className="muted">None in this run.</p>}
        <ol>
          {changes.map((c) => (
            <li key={c.step} className={c.step <= rec.step ? "past" : ""}>
              <button type="button" onClick={() => onJump(c.step)}>
                <span className="mono">t={c.tick}</span> {c.from} → <strong>{c.to}</strong>
                <span className="change-reason">{c.reason}</span>
              </button>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
