import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { RunBundle } from "../types";
import { ApiError, api, loadSample } from "./api";

interface RunState {
  run: RunBundle | null;
  source: string;
  loading: boolean;
  error: string | null;
  apiOnline: boolean | null;
  loadSampleRun: (name: string) => Promise<void>;
  runMission: (opts: { config_name?: string; seed?: number; planner: string }) => Promise<void>;
}

const RunContext = createContext<RunState | null>(null);
const DEFAULT_SAMPLE = "sample_mission";

export function RunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<RunBundle | null>(null);
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  const guarded = useCallback(async (label: string, work: () => Promise<RunBundle>) => {
    setLoading(true);
    setError(null);
    try {
      const bundle = await work();
      setRun(bundle);
      setSource(label);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong loading the mission.");
      if (!(err instanceof ApiError)) console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSampleRun = useCallback((name: string) => guarded(`sample · ${name}`, () => loadSample<RunBundle>(name)), [guarded]);

  const runMission = useCallback(
    (opts: { config_name?: string; seed?: number; planner: string }) =>
      guarded(`live · ${opts.config_name ?? `seed ${opts.seed ?? 0}`} · ${opts.planner}`, async () => {
        const bundle = await api.runMission(opts);
        setApiOnline(true);
        return bundle;
      }),
    [guarded],
  );

  useEffect(() => {
    void loadSampleRun(DEFAULT_SAMPLE);
    api.configs().then(
      () => setApiOnline(true),
      () => setApiOnline(false),
    );
  }, [loadSampleRun]);

  const value = useMemo(
    () => ({ run, source, loading, error, apiOnline, loadSampleRun, runMission }),
    [run, source, loading, error, apiOnline, loadSampleRun, runMission],
  );
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunState {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used inside <RunProvider>");
  return ctx;
}
