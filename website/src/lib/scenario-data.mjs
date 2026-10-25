import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { REPO_ROOT } from "./spec-meta.mjs";

export const SCENARIO_PATH = "docs/demo/scenario.yaml";

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isMessage(value) {
  return typeof value.method === "string" || "result" in value || ("error" in value && isObject(value.error) && "code" in value.error);
}

function collect(value, out) {
  if (Array.isArray(value)) {
    for (const item of value) collect(item, out);
    return;
  }
  if (!isObject(value)) return;
  if (isMessage(value)) {
    out.push(value);
    return;
  }
  for (const item of Object.values(value)) collect(item, out);
}

function firstString(data, keys) {
  if (!isObject(data)) return null;
  for (const key of keys) if (typeof data[key] === "string") return data[key];
  for (const item of Object.values(data)) {
    const found = firstString(item, keys);
    if (found) return found;
  }
  return null;
}

export function scenarioFrom(text, path = SCENARIO_PATH) {
  const data = parse(text);
  const messages = [];
  collect(data, messages);
  if (!messages.some((message) => typeof message.method === "string")) throw new Error(`${path} holds no JSON-RPC requests to show.`);
  return { path, device: firstString(data, ["device", "device_id", "deviceId"]), file: firstString(data, ["file", "device_file", "deviceFile"]), messages };
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

export function jsonLine(value) {
  if (Array.isArray(value)) return `[${value.map(jsonLine).join(", ")}]`;
  if (isObject(value)) return `{${Object.entries(value).map(([key, item]) => `${JSON.stringify(key)}: ${jsonLine(item)}`).join(", ")}}`;
  return JSON.stringify(value) ?? "null";
}

export function scenarioTraceText(scenario = loadScenario()) {
  return scenario.messages.map((message) => `${typeof message.method === "string" ? "→" : "←"} ${jsonLine(message)}`).join("\n");
}
