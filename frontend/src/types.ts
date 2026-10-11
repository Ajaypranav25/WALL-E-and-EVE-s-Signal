// Shapes of the JSON the backend writes (run.json bundle and benchmark.json).

export type Cell = [number, number];
export type EveStatus = "active" | "dormant" | "damaged";
export type ActionKind = "move" | "scan" | "listen" | "inspect" | "recharge" | "end";

export interface Ping {
  bearing_deg: number;
  strength_dbm: number;
}

export interface Detection {
  type: "eve" | "clue" | "decoy";
  id?: string;
  position: Cell;
  status?: EveStatus;
}

export interface ClueContent {
  id: string;
  kind: string;
  position: Cell;
  message: string;
  bearing_deg?: number;
  sector?: string;
  distance_estimate?: number;
  status_hint?: EveStatus;
}

export interface Observation {
  tick: number;
  position: Cell;
  battery: number;
  time_used: number;
  result: string;
  at_charger: boolean;
  detections?: Detection[];
  pings?: Ping[];
  clue?: ClueContent;
  done?: boolean;
  outcome?: string;
}

export interface StrategyChange {
  from: string;
  to: string;
  goal: Cell | null;
  reason: string;
  step: number;
  tick: number;
}

export interface StepRecord {
  step: number;
  tick: number;
  action: { kind: ActionKind; direction?: string } | null;
  decision: {
    mode: string;
    goal: Cell | null;
    reasoning: string;
    source: string;
    considered?: { cell: Cell; utility: number; mass: number; cost: number }[];
  };
  observation: Observation;
  notes: string[];
  state: {
    position: Cell;
    battery: number;
    time_used: number;
    time_left: number;
    mode: string;
    goal: Cell | null;
    map_estimate: Cell;
    map_p: number;
    entropy_bits: number;
    status: Record<EveStatus, number>;
    pending_clues: number;
    decoys_known: number;
  };
  top_cells: { cell: Cell; p: number }[];
  belief: number[];
  strategy_change?: StrategyChange;
}

export interface WorldInfo {
  name: string;
  description: string;
  width: number;
  height: number;
  grid: string[];
  map_known: boolean;
  start: Cell;
  chargers: Cell[];
  eve: { position: Cell; status: EveStatus };
  clues: { id: string; kind: string; position: Cell; misleading: boolean }[];
  decoys: { id: string; position: Cell; power_dbm: number }[];
  initial_signal: {
    bearing_deg: number | null;
    coordinates: Cell | null;
    uncertainty: number;
    strength_dbm: number | null;
    timestamp: number;
  };
  scan_radius: number;
  battery_max: number;
  time_limit: number;
}

export interface Report {
  mission: {
    name: string;
    seed: number;
    planner: string;
    outcome: string;
    outcome_text: string;
    steps: number;
    time_used: number;
    time_limit: number;
    battery_left: number;
    battery_used: number;
    distance_travelled: number;
    recharges: number;
  };
  evidence: {
    initial_signal: WorldInfo["initial_signal"];
    clues_read: ClueContent[];
    clues_detected_unread: { id: string; position: Cell }[];
    listens: number;
    pings_heard: number;
    suspicious_pings: number;
    decoys_identified: { id: string; position: Cell }[];
    eve_sighting: Detection | null;
  };
  inference: {
    location: Cell;
    map_probability: number;
    credible_region_90_cells: number;
    status: EveStatus;
    status_probabilities: Record<EveStatus, number>;
    confidence: number;
    confidence_text: string;
  };
  recommended_next_step: string;
  strategy_changes: StrategyChange[];
  ground_truth: {
    eve_position: Cell;
    eve_status: EveStatus;
    location_error_cells: number;
    status_correct: boolean;
    decoys: { id: string; position: Cell }[];
    clues: { id: string; kind: string; position: Cell; misleading: boolean }[];
  };
}

export interface RunBundle {
  id?: string;
  version: number;
  world: WorldInfo;
  report: Report;
  steps: StepRecord[];
}

export interface BenchSummary {
  success_rate: number;
  stranded_rate: number;
  mean_time_when_found: number | null;
  mean_battery_when_found: number | null;
  mean_location_error: number | null;
  status_accuracy: number;
  decoy_missions_solved: number;
}

export interface BenchResult {
  n: number;
  seed: number;
  planners: string[];
  results: Record<string, { summary: BenchSummary; seconds: number; runs: Record<string, unknown>[] }>;
}

export interface ConfigInfo {
  name: string;
  title: string;
  description: string;
  format: string;
  error?: string;
}
