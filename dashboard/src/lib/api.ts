import type {
  AuditEntry,
  ConfirmationRequest,
  Decision,
  DeviceSummary,
  DeviceView,
  Principal,
  Question,
  Routine,
  RoutineDryRun,
  RoutineSummary,
  Run,
  Status,
  TestStep,
  TokenInfo,
  UnknownDevice,
  WriterSession,
} from "./types";
import type { LogEntry } from "./trace";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const value = (body as { detail: unknown }).detail;
    if (typeof value === "string") return value;
    if (Array.isArray(value) && value[0] && typeof value[0] === "object" && "msg" in value[0]) {
      return String((value[0] as { msg: unknown }).msg);
    }
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-OpenHAL-Request"] = "1";
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const init: RequestInit = { method, headers, credentials: "same-origin" };
  if (body !== undefined) init.body = JSON.stringify(body);
  const response = await fetch(path, init);
  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!response.ok) throw new ApiError(response.status, detail(parsed, `The hub answered ${response.status}.`));
  return parsed as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body: unknown = {}) => request<T>("POST", path, body);

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  whoami: () => get<Principal>("/v1/whoami"),
  pair: (code: string) => post<{ ok: boolean }>("/v1/pair", { code }),
  status: () => get<Status>("/v1/status"),
  devices: () => get<DeviceSummary[]>("/v1/devices"),
  device: (id: string) => get<DeviceView>(`/v1/devices/${encodeURIComponent(id)}`),
  write: (device: string, channel: string, value: unknown, unit?: string) =>
    post<Decision>("/v1/write", unit ? { device, channel, value, unit } : { device, channel, value }),
  action: (device: string, action: string, args: Record<string, unknown>) =>
    post<Decision>("/v1/action", { device, action, args }),
  stop: (reason: string) => post<{ reason: string; devices: { device: string; status: string; detail: string }[] }>("/v1/stop", { reason }),
  unlock: (phrase: string) => post<{ ok: boolean; stopped: boolean }>("/v1/unlock", { phrase }),
  confirmations: (includeDone = false) =>
    get<ConfirmationRequest[]>(`/v1/confirmations${query({ include_done: includeDone || undefined })}`),
  approve: (id: string) => post<Decision>(`/v1/confirmations/${encodeURIComponent(id)}/approve`),
  reject: (id: string, reason: string) =>
    post<ConfirmationRequest>(`/v1/confirmations/${encodeURIComponent(id)}/reject`, { reason }),
  audit: (filters: { device?: string; status?: string; event?: string; limit?: number }) =>
    get<AuditEntry[]>(`/v1/audit${query({ ...filters })}`),
  auditVerify: () => get<{ ok: boolean; broken_at: number | null; head: string | null }>("/v1/audit/verify"),
  routines: () => get<RoutineSummary[]>("/v1/routines"),
  routine: (id: string) => get<Routine>(`/v1/routines/${encodeURIComponent(id)}`),
  routineDryRun: (id: string) => post<RoutineDryRun>(`/v1/routines/${encodeURIComponent(id)}/dry_run`),
  routineEnable: (id: string) => post<Routine>(`/v1/routines/${encodeURIComponent(id)}/enable`),
  routineDisable: (id: string) => post<Routine>(`/v1/routines/${encodeURIComponent(id)}/disable`),
  routineRun: (id: string) => post<Run>(`/v1/routines/${encodeURIComponent(id)}/run`),
  routineApprove: (id: string, device: string) =>
    post<Record<string, unknown>>(`/v1/routines/${encodeURIComponent(id)}/approve`, { device }),
  discover: () => post<{ matched: unknown[]; unknown: UnknownDevice[]; errors: { driver: string; error: string }[] }>("/v1/discover", {}),
  unknownDevices: () => get<UnknownDevice[]>("/v1/discover/unknown"),
  writerStart: (body: { unknown_id?: string; driver?: string; params?: Record<string, unknown>; manual_text?: string }) =>
    post<WriterSession>("/v1/writer/sessions", body),
  writerSession: (id: string) => get<WriterSession>(`/v1/writer/sessions/${encodeURIComponent(id)}`),
  writerPropose: (id: string, draft_yaml: string) =>
    post<WriterSession>(`/v1/writer/sessions/${encodeURIComponent(id)}/propose`, { draft_yaml }),
  writerInterview: (id: string) => get<{ questions: Question[] }>(`/v1/writer/sessions/${encodeURIComponent(id)}/interview`),
  writerAnswers: (id: string, answers: Record<string, unknown>) =>
    post<WriterSession>(`/v1/writer/sessions/${encodeURIComponent(id)}/answers`, { answers }),
  writerTestPlan: (id: string) =>
    get<{ steps: TestStep[]; problems: string[] }>(`/v1/writer/sessions/${encodeURIComponent(id)}/test_plan`),
  writerFinish: (id: string, save_as: string) =>
    post<{ path: string; device_id: string; writable: boolean; bundle: string }>(
      `/v1/writer/sessions/${encodeURIComponent(id)}/finish`,
      { save_as },
    ),
  tokens: () => get<TokenInfo[]>("/v1/tokens"),
  createToken: (name: string, kind: "agent" | "human", scope: string) =>
    post<TokenInfo & { token: string }>("/v1/tokens", { name, kind, scope }),
  revokeToken: (id: string) => request<{ ok: boolean }>("DELETE", `/v1/tokens/${encodeURIComponent(id)}`),
  pairCode: () => post<{ code: string; expires_in_s: number }>("/v1/pair/code"),
  rpcLog: async (since = 0): Promise<LogEntry[] | null> => {
    try {
      const body = await get<LogEntry[] | { entries: LogEntry[] }>(`/v1/rpc/log${query({ since })}`);
      return Array.isArray(body) ? body : body.entries;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
};

export function wsUrl(path: string): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${path}`;
}
