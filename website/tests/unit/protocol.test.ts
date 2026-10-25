import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ERROR_REGISTRY } from "../../src/lib/protocol";
import { SCENARIO_PATH, scenarioFrom, traceOf } from "../../src/lib/scenario";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const read = (path: string) => readFileSync(`${root}${path}`, "utf8");
const adr = read("docs/adr/0015-openhal-hub-protocol.md");
const safety = read("spec/2026-10-24/safety.md");

function adrRegistry() {
  return [...adr.matchAll(/^\| (-32\d{3}) \| ([A-Z_]+) \| ([^|]*)\|/gm)].map((match) => ({
    code: Number(match[1]),
    name: match[2],
    kernelCodes: [...match[3].matchAll(/`([a-z_]+)`/g)].map((code) => code[1]),
  }));
}


describe("error registry", () => {
  it("matches ADR 0015 row for row", () => {
    expect(ERROR_REGISTRY.map(({ code, name, kernelCodes }) => ({ code, name, kernelCodes }))).toEqual(adrRegistry());
  });

  it("matches the registry table in the safety section", () => {
    for (const entry of ERROR_REGISTRY) expect(safety).toMatch(new RegExp(`\\| ${entry.code} \\| ${entry.name} \\|`));
  });
});

const RECORDED = `
device: plant-waterer
file: plant-waterer.hal.yaml
exchanges:
  - request: { jsonrpc: "2.0", id: 1, method: hal/action, params: { device: plant-waterer, action: water, args: { duration: { value: 120, unit: s } } } }
    response:
      jsonrpc: "2.0"
      id: 1
      error: { code: -32010, message: "water duration 120 s exceeds the limit of 30 s", data: { name: LIMIT_EXCEEDED } }
  - request: { jsonrpc: "2.0", id: 2, method: hal/action, params: { device: plant-waterer, action: water, args: { duration: { value: 20, unit: s } } } }
    response: { jsonrpc: "2.0", id: 2, result: { status: done } }
  - notification: { jsonrpc: "2.0", method: hal/value, params: { device: plant-waterer, channel: soil_moisture, value: 46, unit: "%" } }
`;

describe("the recorded scenario", () => {
  it("reads every message in order, whatever the layout", () => {
    const scenario = scenarioFrom(RECORDED);
    expect(scenario.device).toBe("plant-waterer");
    expect(scenario.file).toBe("plant-waterer.hal.yaml");
    expect(traceOf(scenario.messages).map((entry) => entry.kind)).toEqual(["request", "error", "request", "result", "notification"]);
    expect(traceOf(scenario.messages)[1]).toEqual({ kind: "error", code: -32010, name: "LIMIT_EXCEEDED", reason: "water duration 120 s exceeds the limit of 30 s" });
  });

  it("refuses a file with no requests", () => {
    expect(() => scenarioFrom("device: x\n")).toThrow(/no JSON-RPC requests/);
  });

  it("names only registry codes and names", () => {
    if (!existsSync(`${root}${SCENARIO_PATH}`)) return;
    for (const entry of traceOf(scenarioFrom(read(SCENARIO_PATH)).messages)) {
      if (entry.kind === "error") expect(ERROR_REGISTRY.find((item) => item.code === entry.code)?.name).toBe(entry.name);
    }
  });
});
