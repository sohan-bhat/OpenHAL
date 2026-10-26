import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ERROR_REGISTRY } from "../../src/lib/protocol";
import { SCENARIO_PATH, outcome, scenarioFrom, scenarioTrace } from "../../src/lib/scenario";
import { traceText } from "../../src/lib/trace";

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

const expected = JSON.parse(read("website/tests/kernel-parity/expected.json"));

describe("the recorded scenario", () => {
  const scenario = scenarioFrom(read(SCENARIO_PATH));

  it("says what happens in the hub's own words", () => {
    expect(outcome(scenario)).toBe(expected.scenario.outcome);
  });

  it("shows the same lines as openhal.demo.trace", () => {
    const entries = scenarioTrace(scenario);
    const shownLines = traceText(entries).split("\n").map((line) => line.trim()).filter(Boolean);
    for (const line of expected.scenario.lines as string[]) {
      const bare = line.replace(/^[\u2192\u2190]\s*/, "").trim();
      if (!bare || bare.startsWith("{") || bare.startsWith('"args"') || /^hal\/(action|value)/.test(bare) || /^result/.test(bare)) continue;
      expect(shownLines.some((shownLine) => shownLine.replace(/^(->|<-)\s*/, "").replace(/\s+/g, " ").includes(bare.replace(/\s+/g, " ")))).toBe(true);
    }
  });

  it("sends hal/value with the params ADR 0015 names and the recorded value", () => {
    const watered = scenario.record.exchanges.find((exchange) => exchange.soil_moisture);
    const notification = scenarioTrace(scenario).find((entry) => entry.kind === "notification");
    expect(notification).toEqual({
      kind: "notification",
      method: "hal/value",
      params: { device: watered!.request.params.device, channel: "soil_moisture", value: watered!.soil_moisture!.after.value, unit: watered!.soil_moisture!.after.unit },
    });
  });

  it("writes narration as comments, the same way openhal.demo.trace does", () => {
    const notes = scenarioTrace(scenario).filter((entry) => entry.kind === "note");
    expect(notes.length).toBeGreaterThan(0);
    const site = traceText(notes).split("\n");
    const python = (expected.scenario.lines as string[]).filter((line) => line.startsWith("#"));
    expect(site).toEqual(python);
    for (const line of site) expect(line).toMatch(/^# \S/);
  });

  it("sends the recorded requests and names only registry codes", () => {
    const entries = scenarioTrace(scenario);
    expect(entries.filter((entry) => entry.kind === "request")).toHaveLength(scenario.record.exchanges.length);
    for (const entry of entries) {
      if (entry.kind === "error") expect(ERROR_REGISTRY.find((item) => item.code === entry.code)?.name).toBe(entry.name);
    }
  });

  it("refuses a file without exchanges", () => {
    expect(() => scenarioFrom("device: x\n")).toThrow(/no exchanges/);
  });
});
