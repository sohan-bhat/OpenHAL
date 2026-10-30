import { loadScenario, type Scenario } from "../scenario";

/** One request of the recorded run and the hub's answer, as the example page shows them. */
export interface Message {
  id: string;
  by: string;
  note: string;
  method: string;
  request: string;
  response: string;
  refused: boolean;
}

const WIDTH = 64;

const inline = (item: unknown): string => {
  if (item === null || typeof item !== "object") return JSON.stringify(item) ?? "null";
  if (Array.isArray(item)) return item.length ? `[${item.map(inline).join(", ")}]` : "[]";
  const entries = Object.entries(item);
  return entries.length ? `{ ${entries.map(([key, inner]) => `${JSON.stringify(key)}: ${inline(inner)}`).join(", ")} }` : "{}";
};

/**
 * JSON with two spaces of indent, where an object or a list that fits in the room left on its line,
 * out of WIDTH characters, stays on that line.
 */
export function compactJson(value: unknown, indent = 0, room = WIDTH - indent): string {
  const flat = inline(value);
  if (value === null || typeof value !== "object" || flat.length <= room) return flat;
  const pad = " ".repeat(indent + 2);
  const close = " ".repeat(indent);
  if (Array.isArray(value)) return `[\n${value.map((item) => pad + compactJson(item, indent + 2)).join(",\n")}\n${close}]`;
  const entries = Object.entries(value).map(([key, inner]) => {
    const prefix = `${JSON.stringify(key)}: `;
    return pad + prefix + compactJson(inner, indent + 2, WIDTH - indent - 2 - prefix.length);
  });
  return `{\n${entries.join(",\n")}\n${close}}`;
}

const sentence = (text: string) => `${text[0].toUpperCase()}${text.slice(1)}.`;

/** Every request of docs/demo/scenario.yaml with the hub's answer, in the order the run sent them. */
export function messages(scenario: Scenario = loadScenario()): Message[] {
  return scenario.record.exchanges.map((exchange) => ({
    id: String(exchange.id),
    by: String(exchange.by ?? ""),
    note: sentence(String(exchange.before ?? exchange.id)),
    method: exchange.request.method,
    request: compactJson({ method: exchange.request.method, params: exchange.request.params ?? {} }),
    response: compactJson(exchange.error ? { error: exchange.error } : { result: exchange.result }),
    refused: Boolean(exchange.error),
  }));
}

export interface AuditEntry {
  seq: number;
  event: string;
  who: string;
  target: string;
  status: string;
  message: string;
}

/** The audit log's entries as `openhal log` printed them at the end of the run, newest first, and the log's counts in words. */
export function auditLog(scenario: Scenario = loadScenario()): { command: string; entries: AuditEntry[]; counts: string } {
  const audit = (scenario.record as Record<string, any>).audit as { printed_with: string; entries: AuditEntry[]; counts: Record<string, number> };
  const counts = audit.counts;
  return {
    command: audit.printed_with,
    entries: audit.entries.map((entry) => ({ ...entry, seq: Number(entry.seq), message: String(entry.message ?? "") })),
    counts: `${counts.requests} requests, ${counts.refused} refused, ${counts.confirmed_by_a_person} confirmed by a person.`,
  };
}
