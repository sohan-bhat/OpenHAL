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
  const command = record.exchanges.find((exchange) => exchange.request.method !== "hal/read");
  const device = typeof command?.request.params?.device === "string" ? command.request.params.device : null;
  const described = Array.isArray(record.devices) ? record.devices.find((item) => item?.id === device) : null;
  return { path, record, device, file: typeof described?.file === "string" ? described.file : null };
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

const ELIDED = "\u2026";

function resultOf(exchange) {
  const result = exchange.result ?? {};
  if (exchange.request.method === "hal/read") {
    const value = isObject(result.value) && "mimeType" in result.value ? { ...result.value, data: ELIDED } : result.value;
    return { value };
  }
  if (result.status === "pending") return Object.fromEntries(["status", "requestId", "expiresInS"].filter((key) => key in result).map((key) => [key, result[key]]));
  return { status: result.status ?? null };
}

export function exchangeEntries(exchange) {
  const out = [];
  if (typeof exchange.before === "string" && exchange.before) out.push({ kind: "note", text: exchange.before });
  out.push({ kind: "request", method: exchange.request.method, params: exchange.request.params ?? {} });
  if (isObject(exchange.error)) {
    out.push({ kind: "error", code: Number(exchange.error.code), name: String(exchange.error.data?.name ?? ""), reason: String(exchange.error.message ?? "") });
  } else {
    out.push({ kind: "result", result: resultOf(exchange) });
  }
  return out;
}

export function scenarioEntries(scenario = loadScenario()) {
  return scenario.record.exchanges.flatMap(exchangeEntries);
}

/** A quantity as prose shows it, `70 °C` for `{ value: 70, unit: "degC" }`, as openhal.demo.trace.celsius does. */
export function celsius(quantity) {
  return shown(quantity).replace(" degC", " \u00b0C");
}

export function outcome(scenario = loadScenario()) {
  const exchanges = Object.fromEntries(scenario.record.exchanges.map((exchange) => [exchange.id, exchange]));
  const bed = exchanges["bed-warmer"].bed_target;
  const refused = exchanges["nozzle-too-hot"].error.data;
  const approved = exchanges["owner-approves"];
  const by = String(approved.by);
  const person = by.includes(":") ? by.slice(by.indexOf(":") + 1) : "";
  return (
    `You'll see the agent warm the bed from ${celsius(bed.before)} to ${celsius(bed.after)}, ` +
    `have a ${celsius(refused.requested)} nozzle refused at the ${celsius(refused.limit)} limit ` +
    "and pause the print when the camera shows the print has come loose. " +
    `The ${person} then approves the cancel, and the printer's state becomes ${approved.printer.state}.`
  );
}

export function scenarioTraceHtml(scenario = loadScenario()) {
  return traceHtml(scenarioEntries(scenario), { label: "Message trace recorded with openhal demo" });
}
