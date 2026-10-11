import { describe, expect, it } from "vitest";
import type { RunBundle, StepRecord } from "../types";
import { beliefIntensity, knownAt, outcomeTone, pct, rayEnd } from "./replay";

function step(partial: Partial<StepRecord> & { observation: StepRecord["observation"] }): StepRecord {
  return {
    step: 0,
    tick: 0,
    action: null,
    decision: { mode: "search", goal: null, reasoning: "", source: "classical" },
    notes: [],
    state: {} as StepRecord["state"],
    top_cells: [],
    belief: [0, 5, 10, 0],
    ...partial,
  };
}

const obs = (x: number, y: number, extra = {}) => ({ tick: 0, position: [x, y] as [number, number], battery: 10, time_used: 0, result: "", at_charger: false, ...extra });

const run = {
  version: 1,
  world: {} as RunBundle["world"],
  report: {} as RunBundle["report"],
  steps: [
    step({ observation: obs(0, 0) }),
    step({ action: { kind: "move", direction: "E" }, observation: obs(1, 0) }),
    step({ action: { kind: "scan" }, observation: obs(1, 0, { detections: [{ type: "clue", id: "clue-1", position: [2, 1] }, { type: "decoy", id: "decoy-1", position: [3, 3] }] }) }),
    step({
      action: { kind: "inspect" },
      observation: obs(2, 1, { clue: { id: "clue-1", kind: "tracks", position: [2, 1], message: "m" } }),
      strategy_change: { from: "search", to: "investigate", goal: [2, 1], reason: "r", step: 3, tick: 3 },
    }),
    step({ action: { kind: "scan" }, observation: obs(2, 1, { detections: [{ type: "eve", position: [4, 1], status: "active" }] }) }),
  ],
} as RunBundle;

describe("knownAt", () => {
  it("accumulates only what was observed up to the step", () => {
    const early = knownAt(run, 1);
    expect(early.path).toEqual([[0, 0], [1, 0]]);
    expect(early.detectedClues.size).toBe(0);

    const late = knownAt(run, 4);
    expect(late.path).toEqual([[0, 0], [1, 0], [2, 1]]);
    expect(late.scans).toHaveLength(2);
    expect(late.detectedClues.get("clue-1")).toEqual([2, 1]);
    expect(late.readClues.has("clue-1")).toBe(true);
    expect(late.decoys.get("decoy-1")).toEqual([3, 3]);
    expect(late.eveSeen).toEqual([4, 1]);
    expect(late.strategyChanges).toHaveLength(1);
  });

  it("clamps out-of-range steps", () => {
    expect(knownAt(run, 99).path).toHaveLength(3);
    expect(knownAt(run, -5).path).toHaveLength(1);
  });
});

describe("helpers", () => {
  it("normalises belief to the step peak", () => {
    expect(beliefIntensity(run.steps[0])).toEqual([0, 0.5, 1, 0]);
  });

  it("projects rays clockwise from north", () => {
    const [x, y] = rayEnd([5, 5], 90, 2);
    expect(x).toBeCloseTo(7);
    expect(y).toBeCloseTo(5);
    const [nx, ny] = rayEnd([5, 5], 0, 3);
    expect(nx).toBeCloseTo(5);
    expect(ny).toBeCloseTo(2);
  });

  it("formats and classifies", () => {
    expect(pct(0.256, 1)).toBe("25.6%");
    expect(outcomeTone("eve_located")).toBe("good");
    expect(outcomeTone("stranded")).toBe("bad");
    expect(outcomeTone("time_exhausted")).toBe("warn");
  });
});
