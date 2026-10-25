import type { LogEntry } from "./trace";

export const LOG_LIMIT = 2000;

function isEntry(value: unknown): value is LogEntry {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.seq === "number" && (record.direction === "in" || record.direction === "out") && "message" in record;
}

export function parseLiveFrame(data: unknown): LogEntry[] {
  let value = data;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return [];
    }
  }
  if (Array.isArray(value)) return value.filter(isEntry);
  if (isEntry(value)) return [value];
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (isEntry(record.entry)) return [record.entry];
    if (Array.isArray(record.entries)) return record.entries.filter(isEntry);
  }
  return [];
}

export function mergeEntries(existing: LogEntry[], incoming: LogEntry[], limit = LOG_LIMIT): LogEntry[] {
  if (!incoming.length) return existing;
  const last = existing[existing.length - 1];
  const appendOnly = last !== undefined && incoming.every((entry) => entry.seq > last.seq);
  let merged: LogEntry[];
  if (appendOnly) {
    merged = [...existing, ...[...incoming].sort((a, b) => a.seq - b.seq)];
  } else {
    const bySeq = new Map<number, LogEntry>();
    for (const entry of existing) bySeq.set(entry.seq, entry);
    for (const entry of incoming) bySeq.set(entry.seq, entry);
    merged = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
  }
  return merged.length > limit ? merged.slice(merged.length - limit) : merged;
}

export function lastSeq(entries: LogEntry[]): number {
  return entries.length ? entries[entries.length - 1]!.seq : 0;
}

export function isValueNotification(entry: LogEntry): boolean {
  const message = entry.message;
  return !!message && typeof message === "object" && (message as { method?: unknown }).method === "hal/value";
}
