import { SCENARIO_PATH, loadScenario as loadData, scenarioFrom as fromText } from "./scenario-data.mjs";
import type { TraceEntry } from "./trace";

export { SCENARIO_PATH };

export interface Scenario {
  path: string;
  device: string | null;
  file: string | null;
  messages: Array<Record<string, unknown>>;
}

export const scenarioFrom = (text: string, path?: string): Scenario => fromText(text, path) as Scenario;
export const loadScenario = (): Scenario => loadData() as Scenario;

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function traceOf(messages: Array<Record<string, unknown>>): TraceEntry[] {
  return messages.map((message) => {
    if (typeof message.method === "string") {
      const params = isObject(message.params) ? message.params : {};
      return "id" in message ? { kind: "request", method: message.method, params } : { kind: "notification", method: message.method, params };
    }
    if (isObject(message.error)) {
      const data = isObject(message.error.data) ? message.error.data : {};
      return { kind: "error", code: Number(message.error.code), name: String(data.name ?? ""), reason: String(message.error.message ?? "") };
    }
    return { kind: "result", result: message.result };
  });
}

export function scenarioTrace(scenario: Scenario = loadScenario()): TraceEntry[] {
  return traceOf(scenario.messages);
}
