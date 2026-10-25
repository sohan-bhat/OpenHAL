import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { REPO_ROOT } from "./spec-meta.mjs";
import { traceHtml } from "./trace-html.mjs";

export const SCENARIO_PATH = "docs/demo/scenario.yaml";

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function need(condition, path, what) {
  if (!condition) throw new Error(`${path} ${what}`);
}

export function scenarioFrom(text, path = SCENARIO_PATH) {
  const record = parse(text);
  need(isObject(record) && Array.isArray(record.exchanges) && record.exchanges.length > 0, path, "has no exchanges.");
  record.exchanges.forEach((exchange, index) => {
    need(isObject(exchange?.request) && typeof exchange.request.method === "string", path, `exchanges[${index}] has no request method.`);
    need(isObject(exchange.error) || isObject(exchange.result), path, `exchanges[${index}] has neither an error nor a result.`);
  });
  return { path, record, device: typeof record.device === "string" ? record.device : null, file: typeof record.file === "string" ? record.file : null };
}

let cached = null;

export function loadScenario() {
  if (cached) return cached;
  const path = process.env.OPENHAL_SCENARIO ?? join(REPO_ROOT, SCENARIO_PATH);
  if (!existsSync(path)) {
    throw new Error(`${SCENARIO_PATH} is missing. The overview trace, the blog post and every Open Graph image read their values from it.`);
  }
  cached = scenarioFrom(readFileSync(path, "utf8"), path);
  return cached;
}

export function shown(value) {
  if (isObject(value) && "value" in value && value.unit) {
    const magnitude = Number(value.value);
    const text = Number.isInteger(magnitude) ? String(magnitude) : String(Number(magnitude.toPrecision(6)));
    return `${text} ${value.unit === "percent" ? "%" : value.unit}`;
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function exchangeEntries(exchange) {
  const out = [];
  if (typeof exchange.before === "string" && exchange.before) out.push({ kind: "note", text: exchange.before });
  out.push({ kind: "request", method: exchange.request.method, params: exchange.request.params ?? {} });
  if (isObject(exchange.error)) {
    out.push({ kind: "error", code: Number(exchange.error.code), name: String(exchange.error.data?.name ?? ""), reason: String(exchange.error.message ?? "") });
  } else {
    out.push({ kind: "result", result: { status: exchange.result?.status ?? null } });
  }
  const soil = exchange.soil_moisture;
  if (isObject(soil) && soil.before && soil.after) {
    out.push({ kind: "notification", method: "hal/value", params: {}, text: `soil_moisture rises from ${shown(soil.before)} to ${shown(soil.after)}` });
  }
  return out;
}

export function scenarioEntries(scenario = loadScenario()) {
  return scenario.record.exchanges.flatMap(exchangeEntries);
}

export function outcome(scenario = loadScenario()) {
  const [tooLong, , watered] = scenario.record.exchanges;
  const asked = shown(tooLong.request.params.args.duration);
  const duration = shown(watered.request.params.args.duration);
  const soil = watered.soil_moisture;
  return (
    `You'll see the hub refuse a ${asked} watering, hold the pump while the tank is empty, ` +
    `then water for ${duration} as soil moisture rises from ${shown(soil.before)} to ${shown(soil.after)}.`
  );
}

export function scenarioTraceHtml(scenario = loadScenario()) {
  return traceHtml(scenarioEntries(scenario), { note: "Recorded with openhal demo" });
}
