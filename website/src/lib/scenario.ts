import {
  SCENARIO_PATH,
  exchangeEntries as entriesOf,
  loadScenario as loadData,
  outcome as outcomeOf,
  scenarioEntries as allEntries,
  scenarioFrom as fromText,
} from "./scenario-data.mjs";
import type { TraceEntry } from "./trace";

export { SCENARIO_PATH };

export interface Exchange {
  id?: string;
  before?: string;
  request: { method: string; params: Record<string, any> };
  error?: { code: number; message: string; data: Record<string, any> };
  result?: Record<string, any>;
  soil_moisture?: { before: { value: number; unit: string }; after: { value: number; unit: string } };
}

export interface Scenario {
  path: string;
  device: string | null;
  file: string | null;
  record: { exchanges: Exchange[]; [key: string]: unknown };
}

export const scenarioFrom = (text: string, path?: string): Scenario => fromText(text, path) as Scenario;
export const loadScenario = (): Scenario => loadData() as Scenario;
export const exchangeEntries = (exchange: Exchange): TraceEntry[] => entriesOf(exchange) as TraceEntry[];
export const scenarioTrace = (scenario: Scenario = loadScenario()): TraceEntry[] => allEntries(scenario) as TraceEntry[];
export const outcome = (scenario: Scenario = loadScenario()): string => outcomeOf(scenario);
