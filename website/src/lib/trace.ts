import { highlightHtml } from "./highlight.mjs";

export type TraceEntry =
  | { kind: "request"; method: string; params: unknown }
  | { kind: "notification"; method: string; params: unknown }
  | { kind: "result"; result: unknown }
  | { kind: "error"; code: number; name: string; reason: string };

export function inlineJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return value.length ? `[ ${value.map(inlineJson).join(", ")} ]` : "[]";
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) return "{}";
  return `{ ${entries.map(([key, item]) => `${JSON.stringify(key)}: ${inlineJson(item)}`).join(", ")} }`;
}

export function payloadHtml(value: unknown): string {
  return highlightHtml(inlineJson(value), "json");
}

export function arrowSvg(direction: "out" | "in", dashed = false): string {
  const line = direction === "out" ? `<line x1="1" y1="5" x2="11" y2="5"` : `<line x1="7" y1="5" x2="17" y2="5"`;
  const head = direction === "out" ? `<polygon points="18,5 11,1.5 11,8.5"/>` : `<polygon points="0,5 7,1.5 7,8.5"/>`;
  const dash = dashed ? ` stroke-dasharray="2.5 2"` : "";
  return `<svg class="trace-arrow" viewBox="0 0 18 10" width="18" height="10" aria-hidden="true" focusable="false" fill="currentColor">${line} stroke="currentColor" stroke-width="1.5"${dash}/>${head}</svg>`;
}

export function directionWord(entry: TraceEntry): string {
  if (entry.kind === "request") return "Request";
  if (entry.kind === "notification") return "Notification";
  return "Response";
}

export function traceText(entries: TraceEntry[]): string {
  return entries
    .map((entry) => {
      if (entry.kind === "request") return `-> ${entry.method}  ${inlineJson(entry.params)}`;
      if (entry.kind === "notification") return `<- ${entry.method}  ${inlineJson(entry.params)}`;
      if (entry.kind === "result") return `<- result  ${inlineJson(entry.result)}`;
      return `<- error ${entry.code} ${entry.name}\n   ${entry.reason}`;
    })
    .join("\n");
}
