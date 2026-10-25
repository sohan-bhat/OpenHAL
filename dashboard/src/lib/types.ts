export type Hazard = "low" | "medium" | "high";
export type ConfirmTier = "none" | "confirm" | "confirm-each-time";

export interface Principal {
  kind: string;
  name: string;
  scope: string;
}

export interface Status {
  product: string;
  version: string;
  spec: string;
  protocol_version?: string;
  stopped: boolean;
  stop_reason: string | null;
  devices: number;
  connected: number;
  pending_confirmations: number;
  started_at: number | null;
  load_problems: { path: string; problems: string[] }[];
  you: Principal;
}

export interface DeviceSummary {
  id: string;
  name: string;
  model: string | null;
  manufacturer: string | null;
  driver: string;
  hazard: Hazard;
  writable: boolean;
  connected: boolean;
  unavailable: string | null;
  last_error: string | null;
  verification: string;
  source: string | null;
  conformance?: string;
}

export interface LiveValue {
  value: unknown;
  known: boolean;
  age_s?: number;
}

export interface ReadSpec extends LiveValue {
  type: string;
  unit: string | null;
  every_s: number | null;
  stream: boolean | null;
  range: number[] | null;
  values: string[] | null;
}

export interface WriteSpec extends LiveValue {
  type: string;
  unit: string | null;
  min: number | null;
  max: number | null;
  step: number | null;
  max_change_per_s: number | null;
  values: string[] | null;
  confirm: ConfirmTier | null;
  suggested: boolean | null;
}

export interface ArgSpec {
  type?: string;
  unit?: string;
  min?: number;
  max?: number;
  values?: string[];
  default?: unknown;
}

export interface ActionSpec {
  description: string | null;
  args: Record<string, ArgSpec>;
  require: string[];
  effects: string[];
  confirm: ConfirmTier | null;
}

export interface DeviceView extends DeviceSummary {
  unconfirmed: string[];
  warnings: string[];
  path: string | null;
  read: Record<string, ReadSpec>;
  write: Record<string, WriteSpec>;
  actions: Record<string, ActionSpec>;
  interlocks: { if: string | null; require: string; message: string | null }[];
  watchdog: {
    heartbeat_s: number | null;
    on_loss: string | null;
    max_duration: { when: string; for_s: number; then: unknown }[];
  };
  safe_state: Record<string, unknown>[];
  notes: string | null;
}

export interface Decision {
  status: "allowed" | "blocked" | "needs_confirmation" | "done" | "pending" | "failed";
  code: string | null;
  message: string;
  device: string;
  target: string;
  value: unknown;
  unit: string | null;
  limit: Record<string, unknown> | null;
  request_id: string | null;
}

export interface Command {
  kind: "write" | "action";
  device: string;
  channel?: string;
  action?: string;
  value?: unknown;
  args?: Record<string, unknown>;
}

export interface ConfirmationRequest {
  id: string;
  status: string;
  command: Command;
  requested_by: string;
  created_at: number;
  expires_at: number;
  expires_in_s: number;
  dry_run: Decision;
  decided_by: string | null;
  result: Decision | null;
}

export interface AuditEntry {
  seq: number;
  at: number;
  event: string;
  principal: string;
  device: string | null;
  target: string | null;
  status: string | null;
  code: string | null;
  details: Record<string, unknown>;
  hash: string;
}

export interface Run {
  run_id: string;
  routine_id?: string;
  trigger?: string;
  started_at: number;
  finished_at: number | null;
  status: "ok" | "blocked" | "failed" | "running";
  message: string;
  steps: Record<string, unknown>[];
}

export interface RoutineSummary {
  id: string;
  kind: "yaml" | "python";
  enabled: boolean;
  sha256: string;
  devices: string[];
  max_hazard: Hazard;
  triggers: string[];
  drafted_by: string | null;
  enabled_by?: string | null;
  disabled_reason?: string | null;
  last_run: Run | null;
}

export interface RoutineDryRun {
  ok: boolean;
  decisions: Record<string, unknown>[];
  problems: string[];
}

export interface Routine extends RoutineSummary {
  source: string | null;
  source_raw: string;
  history: Run[];
  last_dry_run: RoutineDryRun | null;
}

export interface UnknownDevice {
  id: string;
  address: string;
  driver: string;
  identifiers: Record<string, string>;
  label: string | null;
}

export interface WriterSession {
  id: string;
  status: "detecting" | "drafting" | "interview" | "ready" | "saved";
  detected: Record<string, unknown>;
  sources: (string | null)[];
  draft_yaml: string | null;
  problems: string[];
  unconfirmed: string[];
}

export interface Question {
  id: string;
  channel: string | null;
  field: string;
  prompt: string;
  suggested: unknown;
  unit: string | null;
  reason: string | null;
}

export interface TestStep {
  step: string;
  command: unknown;
  expected: string;
  needs_approval: boolean;
}

export interface TokenInfo {
  token_id: string;
  name: string;
  kind: string;
  scope: string;
  created_at: number;
  revoked: boolean;
}
