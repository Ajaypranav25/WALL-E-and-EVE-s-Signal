import type { BenchResult, ConfigInfo, RunBundle } from "../types";

interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError("The mission API is offline. Start it with `walle serve` to run new missions.");
  }
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.ok ? "The API sent an unreadable response." : `The API is unavailable (HTTP ${res.status}).`);
  }
  if (!res.ok || !body.success || body.data === null) {
    throw new ApiError(body.error ?? `Request failed (HTTP ${res.status}).`);
  }
  return body.data;
}

export const SAMPLE_RUNS: ConfigInfo[] = [
  { name: "sample_mission", title: "Signal in the Dust", description: "Surveyed map, one decoy, six clues.", format: "yaml" },
  { name: "decoy_storm", title: "Decoy Storm", description: "Fog of war, two decoys, stale coordinate fix.", format: "json" },
  { name: "hand_drawn", title: "Hand-drawn Junkyard", description: "Small hand-authored layout.", format: "yaml" },
];

export const api = {
  configs: () => request<ConfigInfo[]>("/api/configs"),
  runMission: (body: { config_name?: string; seed?: number; planner: string }) =>
    request<RunBundle>("/api/missions", { method: "POST", body: JSON.stringify(body) }),
  benchmark: (body: { n: number; seed: number; planners: string[] }) =>
    request<BenchResult>("/api/benchmark", { method: "POST", body: JSON.stringify(body) }),
};

/** Pre-computed runs shipped with the site, so the replay works with no backend. */
export async function loadSample<T>(name: string): Promise<T> {
  const res = await fetch(`samples/${encodeURIComponent(name)}.json`);
  if (!res.ok) throw new ApiError(`Sample ${name} is missing; run \`npm run samples\`.`);
  return (await res.json()) as T;
}
