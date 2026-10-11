// Derives what WALL-E knew at a given step of a run, for the replay view.
import type { Cell, RunBundle, StepRecord } from "../types";

export interface KnownAtStep {
  path: Cell[];
  scans: Cell[];
  detectedClues: Map<string, Cell>;
  readClues: Set<string>;
  decoys: Map<string, Cell>;
  eveSeen: Cell | null;
  strategyChanges: StepRecord[];
}

export const key = (c: Cell): string => `${c[0]},${c[1]}`;

export function knownAt(run: RunBundle, step: number): KnownAtStep {
  const upto = run.steps.slice(0, Math.max(0, Math.min(step, run.steps.length - 1)) + 1);
  const path: Cell[] = [];
  const scans: Cell[] = [];
  const detectedClues = new Map<string, Cell>();
  const readClues = new Set<string>();
  const decoys = new Map<string, Cell>();
  let eveSeen: Cell | null = null;
  const strategyChanges: StepRecord[] = [];

  for (const rec of upto) {
    const pos = rec.observation.position;
    const last = path[path.length - 1];
    if (!last || last[0] !== pos[0] || last[1] !== pos[1]) path.push(pos);
    if (rec.action?.kind === "scan") scans.push(pos);
    for (const d of rec.observation.detections ?? []) {
      if (d.type === "clue" && d.id) detectedClues.set(d.id, d.position);
      if (d.type === "decoy" && d.id) decoys.set(d.id, d.position);
      if (d.type === "eve") eveSeen = d.position;
    }
    if (rec.observation.clue) readClues.add(rec.observation.clue.id);
    if (rec.strategy_change) strategyChanges.push(rec);
  }
  return { path, scans, detectedClues, readClues, decoys, eveSeen, strategyChanges };
}

/** Belief values for one step, normalised to the step's peak so the heatmap keeps contrast. */
export function beliefIntensity(rec: StepRecord): number[] {
  const peak = Math.max(1, ...rec.belief);
  return rec.belief.map((v) => v / peak);
}

/** Endpoint of a ping ray of the given length, using bearings clockwise from north. */
export function rayEnd(origin: Cell, bearingDeg: number, length: number): [number, number] {
  const rad = (bearingDeg * Math.PI) / 180;
  return [origin[0] + Math.sin(rad) * length, origin[1] - Math.cos(rad) * length];
}

export const pct = (v: number, digits = 0): string => `${(v * 100).toFixed(digits)}%`;

export function outcomeTone(outcome: string): "good" | "warn" | "bad" {
  if (outcome === "eve_located") return "good";
  if (outcome === "stranded") return "bad";
  return "warn";
}
