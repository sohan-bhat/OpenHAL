import { parse } from "yaml";
import { registryByName } from "./protocol";
import type { TraceEntry } from "./trace";

export interface Scenario {
  device: string;
  channel: string;
  unit: string;
  current: number;
  requested: number;
  limit: number;
  rate: number;
  granted: number;
  readBack: number;
  file: string;
  confirmedBy: string;
  confirmedAt: string;
}

export const DEFAULT_SCENARIO: Scenario = {
  device: "desk-fan",
  channel: "fan_speed",
  unit: "%",
  current: 20,
  requested: 150,
  limit: 100,
  rate: 20,
  granted: 60,
  readBack: 60,
  file: "desk-fan.hal.yaml",
  confirmedBy: "sohan",
  confirmedAt: "2026-10-24",
};

const files = import.meta.glob<string>("../../../docs/demo/scenario.yaml", { query: "?raw", import: "default", eager: true });

function find(data: unknown, keys: string[]): unknown {
  if (!data || typeof data !== "object") return undefined;
  for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
    if (keys.includes(key.toLowerCase())) return value;
    const nested = find(value, keys);
    if (nested !== undefined) return nested;
  }
  return undefined;
}

function number(value: unknown, fallback: number): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const match = /-?\d+(\.\d+)?/.exec(value);
    if (match) return Number(match[0]);
  }
  return fallback;
}

export function scenarioFrom(text: string | undefined): Scenario {
  if (!text) return DEFAULT_SCENARIO;
  const data = parse(text) as unknown;
  const pick = (keys: string[], fallback: number) => number(find(data, keys), fallback);
  const str = (keys: string[], fallback: string) => {
    const value = find(data, keys);
    return typeof value === "string" ? value : fallback;
  };
  return {
    device: str(["device"], DEFAULT_SCENARIO.device),
    channel: str(["channel"], DEFAULT_SCENARIO.channel),
    unit: DEFAULT_SCENARIO.unit,
    current: pick(["current"], DEFAULT_SCENARIO.current),
    requested: pick(["requested"], DEFAULT_SCENARIO.requested),
    limit: pick(["limit", "max"], DEFAULT_SCENARIO.limit),
    rate: pick(["rate", "max_change_per_s"], DEFAULT_SCENARIO.rate),
    granted: pick(["granted"], DEFAULT_SCENARIO.granted),
    readBack: pick(["read_back", "readback", "readBack"], DEFAULT_SCENARIO.readBack),
    file: str(["file"], DEFAULT_SCENARIO.file),
    confirmedBy: str(["confirmed_by", "confirmedby"], DEFAULT_SCENARIO.confirmedBy),
    confirmedAt: str(["confirmed_at", "confirmedat"], DEFAULT_SCENARIO.confirmedAt),
  };
}

export const SCENARIO: Scenario = scenarioFrom(Object.values(files)[0]);

export function scenarioTrace(scenario: Scenario = SCENARIO): TraceEntry[] {
  const limitExceeded = registryByName("LIMIT_EXCEEDED");
  const q = (value: number) => `${value} ${scenario.unit}`;
  return [
    { kind: "request", method: "hal/write", params: { device: scenario.device, channel: scenario.channel, value: q(scenario.requested) } },
    {
      kind: "error",
      code: limitExceeded.code,
      name: limitExceeded.name,
      reason: `${scenario.channel} ${q(scenario.requested)} exceeds the limit of ${q(scenario.limit)} (${scenario.file}, confirmed by ${scenario.confirmedBy} ${scenario.confirmedAt})`,
    },
    { kind: "request", method: "hal/write", params: { device: scenario.device, channel: scenario.channel, value: q(scenario.granted) } },
    { kind: "result", result: { status: "done", value: scenario.readBack, unit: scenario.unit } },
  ];
}
