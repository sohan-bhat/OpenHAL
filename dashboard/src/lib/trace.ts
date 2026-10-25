import { fromCode } from "./protocol";
import { compareText } from "./text";

export type PrincipalKind = "human" | "agent" | "routine" | "system" | "unknown";

export interface PrincipalInfo {
  kind: PrincipalKind;
  name: string;
  label: string;
}

export interface LogEntry {
  seq: number;
  at: number | string | null;
  direction: "in" | "out";
  client: string | null;
  principal: string | { kind?: string; name?: string; scope?: string } | null;
  message: unknown;
}

export type RowKind = "request" | "result" | "error" | "notification" | "invalid";
export type Arrow = "right" | "left" | "right-dashed" | "left-dashed";
export type Tone = "method" | "result" | "pending" | "error" | "plain";
export type Outcome = "granted" | "pending" | "error" | "notification" | "open";

export interface TraceRow {
  seq: number;
  at: Date | null;
  client: string;
  principal: PrincipalInfo;
  direction: "in" | "out";
  arrow: Arrow;
  kind: RowKind;
  head: string;
  errorCode?: number;
  errorName?: string;
  tone: Tone;
  method?: string;
  id?: string | number | null;
  payload?: unknown;
  summary?: unknown;
  hasPayload: boolean;
  reason?: string;
  devices: string[];
  outcome: Outcome;
  startsExchange: boolean;
}

export interface TraceFilters {
  client: string;
  device: string;
  method: string;
  outcome: string;
}

export const NO_FILTERS: TraceFilters = { client: "", device: "", method: "", outcome: "" };

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function principalInfo(principal: LogEntry["principal"]): PrincipalInfo {
  if (typeof principal === "string") {
    const [kind, ...rest] = principal.split(":");
    const known = ["human", "agent", "routine", "system"].includes(kind ?? "");
    return {
      kind: known ? (kind as PrincipalKind) : "unknown",
      name: known ? rest.join(":") : principal,
      label: principal,
    };
  }
  if (isObject(principal)) {
    const kind = typeof principal.kind === "string" ? principal.kind : "unknown";
    const name = typeof principal.name === "string" ? principal.name : "";
    const known = ["human", "agent", "routine", "system"].includes(kind);
    return { kind: known ? (kind as PrincipalKind) : "unknown", name, label: name ? `${kind}:${name}` : kind };
  }
  return { kind: "unknown", name: "", label: "unknown" };
}

export function parseTime(at: LogEntry["at"]): Date | null {
  if (at === null || at === undefined) return null;
  if (typeof at === "number") return new Date(at > 1e12 ? at : at * 1000);
  const parsed = new Date(at);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatTime(date: Date | null): string {
  if (!date) return "";
  const pad = (value: number, size = 2) => String(value).padStart(size, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}`;
}

export function clientOf(entry: LogEntry): string {
  if (entry.client) return entry.client;
  const message = entry.message;
  if (isObject(message) && message.method === "hal/initialize" && isObject(message.params)) {
    const info = message.params.clientInfo;
    if (isObject(info) && typeof info.name === "string" && info.name) return info.name;
  }
  return "unnamed client";
}

function idKey(client: string, id: unknown): string {
  return `${client}|${JSON.stringify(id)}`;
}

export function devicesIn(value: unknown): string[] {
  const found = new Set<string>();
  const visit = (node: unknown, depth: number) => {
    if (depth > 4 || node === null || typeof node !== "object") return;
    if (Array.isArray(node)) {
      for (const item of node.slice(0, 50)) visit(item, depth + 1);
      return;
    }
    const record = node as Json;
    if (typeof record.device === "string") found.add(record.device);
    if (isObject(record.device) && typeof record.device.id === "string") found.add(record.device.id);
    for (const key of ["params", "result", "error", "data", "command", "request", "items", "readings", "commands", "steps", "decisions", "devices"]) {
      if (key in record) visit(record[key], depth + 1);
    }
  };
  visit(value, 0);
  return [...found];
}

interface RequestInfo {
  method: string;
  devices: string[];
  outcome: Outcome;
}

function resultOutcome(result: unknown): Outcome {
  if (isObject(result) && result.status === "pending") return "pending";
  return "granted";
}

export function buildTrace(entries: LogEntry[]): TraceRow[] {
  const sorted = [...entries].sort((a, b) => a.seq - b.seq);
  const requests = new Map<string, RequestInfo>();
  for (const entry of sorted) {
    const message = entry.message;
    if (!isObject(message)) continue;
    const client = clientOf(entry);
    if (entry.direction === "in" && typeof message.method === "string" && "id" in message) {
      requests.set(idKey(client, message.id), { method: message.method, devices: devicesIn(message), outcome: "open" });
    }
  }
  for (const entry of sorted) {
    const message = entry.message;
    if (!isObject(message) || entry.direction !== "out" || typeof message.method === "string") continue;
    const request = requests.get(idKey(clientOf(entry), message.id));
    if (!request) continue;
    request.outcome = "error" in message ? "error" : resultOutcome(message.result);
  }
  return sorted.map((entry) => toRow(entry, requests));
}

function toRow(entry: LogEntry, requests: Map<string, RequestInfo>): TraceRow {
  const client = clientOf(entry);
  const base = {
    seq: entry.seq,
    at: parseTime(entry.at),
    client,
    principal: principalInfo(entry.principal),
    direction: entry.direction,
  };
  const message = entry.message;
  if (!isObject(message)) {
    return {
      ...base,
      arrow: entry.direction === "in" ? "right" : "left",
      kind: "invalid",
      head: "invalid",
      tone: "plain",
      payload: message,
      hasPayload: true,
      devices: [],
      outcome: "error",
      startsExchange: entry.direction === "in",
    };
  }
  if (typeof message.method === "string") {
    const isRequest = "id" in message;
    const params = message.params;
    const request = isRequest ? requests.get(idKey(client, message.id)) : undefined;
    const row: TraceRow = {
      ...base,
      arrow: entry.direction === "in" ? (isRequest ? "right" : "right-dashed") : "left-dashed",
      kind: isRequest ? "request" : "notification",
      head: message.method,
      tone: "method",
      method: message.method,
      id: isRequest ? (message.id as string | number | null) : undefined,
      payload: params,
      hasPayload: params !== undefined,
      devices: devicesIn(message),
      outcome: isRequest ? (request?.outcome ?? "open") : notificationOutcome(message.method),
      startsExchange: isRequest || entry.direction === "out",
    };
    if (message.method === "hal/blocked" && isObject(params) && isObject(params.error)) {
      const error = params.error;
      if (typeof error.message === "string") row.reason = error.message;
      const code = typeof error.code === "number" ? error.code : undefined;
      const name = typeof error.name === "string" ? error.name : errorName(error);
      if (code !== undefined) row.errorCode = code;
      if (name) row.errorName = name;
      row.summary = { device: params.device, target: params.target };
    }
    return row;
  }
  const request = requests.get(idKey(client, message.id));
  const devices = request?.devices ?? [];
  if ("error" in message && isObject(message.error)) {
    const error = message.error;
    const code = typeof error.code === "number" ? error.code : 0;
    const name = errorName(error);
    const data = isObject(error.data) ? error.data : undefined;
    const extraDevices = data && typeof data.device === "string" ? [data.device] : [];
    const row: TraceRow = {
      ...base,
      arrow: "left",
      kind: "error",
      head: name ? `error ${code} ${name}` : `error ${code}`,
      errorCode: code,
      tone: "error",
      id: message.id as string | number | null,
      hasPayload: false,
      devices: [...new Set([...devices, ...extraDevices])],
      outcome: "error",
      startsExchange: !request,
    };
    if (name) row.errorName = name;
    if (request) row.method = request.method;
    if (typeof error.message === "string") row.reason = error.message;
    return row;
  }
  const outcome = resultOutcome(message.result);
  const row: TraceRow = {
    ...base,
    arrow: "left",
    kind: "result",
    head: "result",
    tone: outcome === "pending" ? "pending" : "result",
    id: message.id as string | number | null,
    payload: message.result,
    hasPayload: true,
    devices,
    outcome,
    startsExchange: !request,
  };
  if (request) row.method = request.method;
  return row;
}

function errorName(error: Json): string | undefined {
  const data = isObject(error.data) ? error.data : undefined;
  if (data && typeof data.name === "string") return data.name;
  return fromCode(typeof error.code === "number" ? error.code : undefined)?.name;
}

function notificationOutcome(method: string): Outcome {
  if (method === "hal/blocked") return "error";
  if (method === "hal/confirmationRequested") return "pending";
  return "notification";
}

export function filterRows(rows: TraceRow[], filters: TraceFilters): TraceRow[] {
  return rows.filter((row) => {
    if (filters.client && row.client !== filters.client) return false;
    if (filters.device && !row.devices.includes(filters.device)) return false;
    if (filters.method && row.method !== filters.method) return false;
    if (filters.outcome && row.outcome !== filters.outcome) return false;
    return true;
  });
}

export interface FilterOptions {
  clients: string[];
  devices: string[];
  methods: string[];
}

export function filterOptions(rows: TraceRow[]): FilterOptions {
  const clients = new Set<string>();
  const devices = new Set<string>();
  const methods = new Set<string>();
  for (const row of rows) {
    clients.add(row.client);
    for (const device of row.devices) devices.add(device);
    if (row.method) methods.add(row.method);
  }
  const sort = (values: Set<string>) => [...values].sort(compareText);
  return { clients: sort(clients), devices: sort(devices), methods: sort(methods) };
}

export function plainTrace(rows: TraceRow[]): string {
  const lines: string[] = [];
  for (const row of rows) {
    if (row.startsExchange && lines.length) lines.push("");
    const arrow = row.arrow.startsWith("right") ? "->" : "<-";
    const payload = row.hasPayload ? ` ${stringifyCompact(row.payload)}` : "";
    lines.push(`${arrow} ${row.head.padEnd(12)}${payload}`.trimEnd());
    if (row.reason) lines.push(`${" ".repeat(15)}${row.reason}`);
  }
  return lines.join("\n");
}

export type TokenType = "punct" | "key" | "string" | "number" | "boolean" | "null" | "space" | "more";

export interface Token {
  type: TokenType;
  text: string;
}

export function tokenizeJson(value: unknown, limit = 4000): Token[] {
  const tokens: Token[] = [];
  let length = 0;
  let truncated = false;
  const push = (type: TokenType, text: string) => {
    if (truncated) return;
    if (length + text.length > limit) {
      truncated = true;
      tokens.push({ type: "more", text: " …" });
      return;
    }
    length += text.length;
    const last = tokens[tokens.length - 1];
    if (last && last.type === type && (type === "punct" || type === "space")) last.text += text;
    else tokens.push({ type, text });
  };
  const visit = (node: unknown) => {
    if (truncated) return;
    if (node === null || node === undefined) push("null", "null");
    else if (typeof node === "string") push("string", JSON.stringify(node));
    else if (typeof node === "number") push("number", Number.isFinite(node) ? String(node) : "null");
    else if (typeof node === "boolean") push("boolean", String(node));
    else if (Array.isArray(node)) {
      if (!node.length) return push("punct", "[]");
      push("punct", "[");
      node.forEach((item, index) => {
        if (index) {
          push("punct", ",");
          push("space", " ");
        }
        visit(item);
      });
      push("punct", "]");
    } else if (typeof node === "object") {
      const keys = Object.keys(node as Json);
      if (!keys.length) return push("punct", "{}");
      push("punct", "{");
      push("space", " ");
      keys.forEach((key, index) => {
        if (index) {
          push("punct", ",");
          push("space", " ");
        }
        push("key", JSON.stringify(key));
        push("punct", ":");
        push("space", " ");
        visit((node as Json)[key]);
      });
      push("space", " ");
      push("punct", "}");
    } else push("string", JSON.stringify(String(node)));
  };
  visit(value);
  return tokens;
}

export function stringifyCompact(value: unknown): string {
  return tokenizeJson(value, Number.POSITIVE_INFINITY)
    .map((token) => token.text)
    .join("");
}
