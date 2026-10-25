import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Kernel, agent, label, loadDeviceFile } from "../../src/lib/kernel";
import { parseDeviceYaml } from "../../src/lib/kernel/yaml";
import { decisionWire, errorFor, responseFor } from "../../src/lib/playground/rpc";
import { ERROR_REGISTRY } from "../../src/lib/protocol";
import { DEFAULT_SCENARIO, scenarioTrace } from "../../src/lib/scenario";
import { traceJson } from "../../src/lib/trace-block";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const read = (path: string) => readFileSync(`${root}${path}`, "utf8");
const adr = read("docs/adr/0015-openhal-hub-protocol.md");
const messages = read("spec/2026-10-24/basic/messages.md");
const safety = read("spec/2026-10-24/safety.md");

function adrRegistry() {
  return [...adr.matchAll(/^\| (-32\d{3}) \| ([A-Z_]+) \| ([^|]*)\|/gm)].map((match) => ({
    code: Number(match[1]),
    name: match[2],
    kernelCodes: [...match[3].matchAll(/`([a-z_]+)`/g)].map((code) => code[1]),
  }));
}

function specExample(after: string): Record<string, any>[] {
  const start = messages.indexOf(after);
  const block = /```json\n([\s\S]*?)```/.exec(messages.slice(start));
  if (start === -1 || !block) throw new Error(`No example after ${after}`);
  return traceJson(block[1]) as Record<string, any>[];
}

const DESK_FAN = `
openhal: "0.1"
device: Desk fan controller
id: desk-fan
connect: { openhal-firmware: auto }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: sohan, at: 2026-10-24 }
`;

function deskFan(current: number) {
  let now = 1000;
  const kernel = new Kernel(() => now);
  const file = loadDeviceFile(parseDeviceYaml(DESK_FAN));
  kernel.register(file, { fan_speed: current });
  kernel.connect("desk-fan");
  return { kernel, file, advance: (seconds: number) => (now += seconds) };
}

describe("error registry", () => {
  it("matches ADR 0015 row for row", () => {
    expect(ERROR_REGISTRY.map(({ code, name, kernelCodes }) => ({ code, name, kernelCodes }))).toEqual(adrRegistry());
  });

  it("matches the registry table in the safety section", () => {
    for (const entry of ERROR_REGISTRY) expect(safety).toMatch(new RegExp(`\\| ${entry.code} \\| ${entry.name} \\|`));
  });
});

describe("the canonical scenario", () => {
  const claude = agent("claude", "control_low");

  it("answers a blocked write exactly as the spec's example", () => {
    const { kernel, file } = deskFan(20);
    const [request, response] = specExample("A blocked write.");
    const command = { kind: "write" as const, ...request.params };
    const decision = kernel.execute(command, claude);
    expect(errorFor(decision, command, file, label(claude))).toEqual(response.error);
  });

  it("answers a granted write exactly as the spec's example", () => {
    const { kernel, file, advance } = deskFan(20);
    advance(5);
    const [request, response] = specExample("A granted write.");
    const command = { kind: "write" as const, ...request.params };
    const entry = responseFor(kernel.execute(command, claude), command, file, 300, label(claude));
    expect(entry).toEqual({ kind: "result", result: response.result });
  });

  it("puts the same reason on the home page trace", () => {
    const { kernel, file } = deskFan(DEFAULT_SCENARIO.current);
    const command = { kind: "write" as const, device: "desk-fan", channel: "fan_speed", value: "150 %" };
    const error = errorFor(kernel.execute(command, claude), command, file);
    const shown = scenarioTrace(DEFAULT_SCENARIO)[1];
    expect(shown).toEqual({ kind: "error", code: error.code, name: error.data.name, reason: error.message });
    expect(safety).toContain(error.message);
  });

  it("reports a dry run decision with its registry error", () => {
    const { kernel, file } = deskFan(20);
    const command = { kind: "write" as const, device: "desk-fan", channel: "fan_speed", value: "150 %" };
    const [decision] = kernel.dryRun([command], claude);
    const wire = decisionWire(decision, command, file, label(claude));
    expect(wire).toMatchObject({ status: "blocked", target: "write:fan_speed", error: { code: -32010, data: { name: "LIMIT_EXCEEDED" } } });
  });
});
