import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { shown } from "../scenario-data.mjs";
import { loadScenario, type Exchange, type Scenario } from "../scenario";
import { REPO_ROOT } from "../spec-meta.mjs";
import { reasonLines } from "../trace-html.mjs";
import type { ShotId } from "./script";

export interface Refusal {
  name: string;
  reason: string;
}

export interface StoryFacts {
  device: string;
  driver: string;
  file: string;
  method: string;
  action: string;
  asked: string;
  ran: string;
  min: string;
  max: string;
  runs: string;
  window: string;
  condition: string;
  confirmed: string;
  tooLong: Refusal;
  empty: Refusal;
  status: string;
  tank: { low: string; ok: string };
  soil: { channel: string; before: number; after: number; unit: string; text: string; reading: string };
}

interface DeviceFile {
  device: string;
  connect: Record<string, unknown>;
  read: Record<string, { values?: string[]; unit?: string }>;
  actions: Record<string, { require?: Array<{ condition?: string } | string> }>;
}

const NBSP = " ";

/** Keeps a number on the same line as its unit. */
export const nb = (text: string): string => text.replace(/(\d) (?=%|[a-zA-Z]+\b)/g, `$1${NBSP}`);

const value = (exchange: Exchange): string => shown(exchange.request.params.args.duration);

function refusal(exchange: Exchange): Refusal {
  const error = exchange.error!;
  return { name: String(error.data.name), reason: reasonLines(String(error.message))[0] };
}

export function readDeviceFile(path = join(REPO_ROOT, "examples", "plant-waterer", "plant-waterer.hal.yaml")): DeviceFile {
  return parse(readFileSync(path, "utf8")) as DeviceFile;
}

/** Every word and number the landing story shows, from docs/demo/scenario.yaml and the plant waterer's device file. */
export function storyFacts(scenario: Scenario = loadScenario(), file: DeviceFile = readDeviceFile()): StoryFacts {
  const record = scenario.record as Scenario["record"] & {
    limits: { water_duration: { min: unknown; max: unknown }; water_runs: { count: number; per: unknown } };
    confirmed: { by: string; at: string };
  };
  const [tooLong, empty, watered] = record.exchanges;
  const action = String(tooLong.request.params.action);
  const require = file.actions[action]?.require ?? [];
  const condition = require.map((item) => (typeof item === "string" ? item : item.condition ?? "")).find(Boolean) ?? "";
  const [channel, wanted] = condition.split(/\s*==\s*/);
  const values = file.read[channel]?.values ?? [];
  const soil = watered.soil_moisture!;
  const soilChannel = Object.keys(file.read).find((name) => name !== channel) ?? "soil_moisture";
  return {
    device: file.device,
    driver: Object.keys(file.connect)[0],
    file: scenario.file ?? "",
    method: tooLong.request.method,
    action,
    asked: value(tooLong),
    ran: value(watered),
    min: shown(record.limits.water_duration.min),
    max: shown(record.limits.water_duration.max),
    runs: String(record.limits.water_runs.count),
    window: shown(record.limits.water_runs.per),
    condition,
    confirmed: `confirmed by ${record.confirmed.by} ${record.confirmed.at}`,
    tooLong: refusal(tooLong),
    empty: refusal(empty),
    status: String(watered.result?.status ?? ""),
    tank: { low: values.find((item) => item !== wanted) ?? "", ok: wanted ?? "" },
    soil: {
      channel: soilChannel,
      before: soil.before.value,
      after: soil.after.value,
      unit: soil.before.unit,
      text: `${soilChannel} ${shown(soil.before)} to ${shown(soil.after)}`,
      reading: `${soilChannel} ${shown(soil.after)}`,
    },
  };
}

/** What the story says at each shot, in plain words. */
export function storyLines(facts: StoryFacts): Record<ShotId, string> {
  const soil = (n: number) => shown({ value: n, unit: facts.soil.unit });
  return {
    wide: "Watch an AI water a plant.",
    ask: nb(`The AI asks the plant waterer to run for ${facts.asked}.`),
    check: nb(`Too long. A person set the limit at ${facts.max}, so the safety kernel says no.`),
    reply: "The AI gets the reason back. The pump never moved.",
    dry: "Later, the tank runs dry.",
    hold: nb(`The AI asks for ${facts.ran}. The kernel sees the empty tank and holds the pump.`),
    refill: "Someone refills the tank.",
    water: nb(`Now every check passes, and the pump runs for ${facts.ran}.`),
    soil: nb(`Soil moisture climbs from ${soil(facts.soil.before)} to ${soil(facts.soil.after)}.`),
    done: "The AI hears back. The plant is watered.",
    end: "Every command to every device takes this path.",
  };
}
