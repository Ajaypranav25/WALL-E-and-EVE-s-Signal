import { useEffect } from "react";

const SPEEDS = [1, 2, 4, 8];
const BASE_INTERVAL_MS = 320;

interface Props {
  step: number;
  total: number;
  tick: number;
  playing: boolean;
  speed: number;
  marks: number[];
  onStep: (s: number) => void;
  onPlaying: (p: boolean) => void;
  onSpeed: (s: number) => void;
}

export function Timeline({ step, total, tick, playing, speed, marks, onStep, onPlaying, onSpeed }: Props) {
  const last = total - 1;

  useEffect(() => {
    if (!playing) return;
    if (step >= last) {
      onPlaying(false);
      return;
    }
    const id = window.setTimeout(() => onStep(step + 1), BASE_INTERVAL_MS / speed);
    return () => window.clearTimeout(id);
  }, [playing, step, last, speed, onStep, onPlaying]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, select, textarea")) return;
      if (e.key === " ") {
        e.preventDefault();
        onPlaying(!playing);
      } else if (e.key === "ArrowRight") onStep(Math.min(last, step + 1));
      else if (e.key === "ArrowLeft") onStep(Math.max(0, step - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playing, step, last, onStep, onPlaying]);

  return (
    <div className="timeline">
      <div className="timeline-buttons">
        <button className="btn btn-ghost btn-icon" type="button" aria-label="Back to start" onClick={() => onStep(0)}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2v10M12 2 5 7l7 5Z" fill="currentColor" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /></svg>
        </button>
        <button className="btn btn-ghost btn-icon" type="button" aria-label="Previous step" onClick={() => onStep(Math.max(0, step - 1))}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M9 2 4 7l5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <button className="btn btn-solid play" type="button" aria-label={playing ? "Pause" : "Play"} onClick={() => onPlaying(!playing)}>
          {playing ? (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><rect x="2.5" y="2" width="3" height="10" rx="1" fill="currentColor" /><rect x="8.5" y="2" width="3" height="10" rx="1" fill="currentColor" /></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 2v10l9-5Z" fill="currentColor" /></svg>
          )}
          {playing ? "Pause" : step >= last ? "Replay" : "Play"}
        </button>
        <button className="btn btn-ghost btn-icon" type="button" aria-label="Next step" onClick={() => onStep(Math.min(last, step + 1))}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="m5 2 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <div className="speed" role="group" aria-label="Playback speed">
          {SPEEDS.map((s) => (
            <button key={s} type="button" className="pill pill-sm" aria-pressed={speed === s} onClick={() => onSpeed(s)}>
              {s}×
            </button>
          ))}
        </div>
      </div>
      <div className="scrubber">
        <input
          type="range"
          min={0}
          max={last}
          value={step}
          aria-label="Mission step"
          onChange={(e) => {
            onPlaying(false);
            onStep(Number(e.target.value));
          }}
        />
        <div className="scrub-marks" aria-hidden="true">
          {marks.map((m) => (
            <span key={m} style={{ left: `${(m / Math.max(1, last)) * 100}%` }} />
          ))}
        </div>
      </div>
      <p className="timeline-meta">
        Step <strong>{step}</strong> / {last} · tick {tick}
        <span className="hint"> · Space plays, ← → step</span>
      </p>
    </div>
  );
}
