import { arrowSvg as arrow, directionWord as word, inlineJson as json, payloadHtml as payload, reasonLines as lines } from "./trace-html.mjs";

export type TraceEntry =
  | { kind: "request"; method: string; params: unknown }
  | { kind: "notification"; method: string; params: unknown; text?: string }
  | { kind: "result"; result: unknown }
  | { kind: "error"; code: number; name: string; reason: string }
  | { kind: "note"; text: string };

export const inlineJson = (value: unknown): string => json(value);
export const payloadHtml = (value: unknown): string => payload(value);
export const arrowSvg = (direction: "out" | "in", dashed = false): string => arrow(direction, dashed);
export const directionWord = (entry: TraceEntry): string => word(entry);
export const reasonLines = (reason: string): string[] => lines(reason);

export function traceText(entries: TraceEntry[]): string {
  return entries
    .map((entry) => {
      if (entry.kind === "note") return `# ${entry.text}`;
      if (entry.kind === "request") return `-> ${entry.method}  ${inlineJson(entry.params)}`;
      if (entry.kind === "notification") return `<- ${entry.method}  ${entry.text ?? inlineJson(entry.params)}`;
      if (entry.kind === "result") return `<- result  ${inlineJson(entry.result)}`;
      return `<- error ${entry.code} ${entry.name}\n${reasonLines(entry.reason).map((part) => `   ${part}`).join("\n")}`;
    })
    .join("\n");
}
