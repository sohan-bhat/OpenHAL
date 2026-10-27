import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { IDS, TOLD, amount, humane, nb, readDeviceFile, storyFacts, storyLines, storyTrace } from "../../src/lib/story/facts";
import { COUNTED, PLACED, STEPS, TOTAL, step, stepAt, type StepId } from "../../src/lib/story/script";
import { AGENT, CAMERA, DRIVER, FILLS, HUB, PRINTER, WIRES } from "../../src/lib/story/timeline";
import type { Exchange, Scenario } from "../../src/lib/scenario";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = readFileSync(scenarioFile, "utf8");
const fresh = () => scenarioFrom(recorded) as Scenario;
const byId = (scenario: Scenario, id: string) => scenario.record.exchanges.find((exchange) => exchange.id === id)!;
const quantity = (exchange: Exchange) => amount(exchange.request.params.value, exchange.request.params.unit);
const index = (id: StepId) => step(id).index;

describe("the story's steps", () => {
  it("run one after another, and the visitor counts every one after the title", () => {
    expect(PLACED[0].from).toBe(0);
    for (let i = 1; i < PLACED.length; i++) expect(PLACED[i].from).toBe(PLACED[i - 1].to);
    expect(TOTAL).toBe(STEPS.reduce((sum, item) => sum + item.length, 0));
    expect(COUNTED.map((item) => item.id)).toEqual(STEPS.slice(1).map((item) => item.id));
    for (const item of PLACED) {
      expect(stepAt(item.from)).toBe(item.index);
      expect(stepAt(item.to - 0.01)).toBe(item.index);
    }
    expect(stepAt(TOTAL + 50)).toBe(PLACED.length - 1);
  });

  it("show every piece in steps that exist", () => {
    const ids = new Set(STEPS.map((item) => item.id));
    const lists = [
      AGENT.person,
      ...Object.values(AGENT.asks),
      ...Object.values(AGENT.hears),
      ...Object.values(HUB),
      ...Object.values(DRIVER),
      ...Object.values(PRINTER),
      ...Object.values(CAMERA),
      ...Object.values(WIRES),
    ];
    for (const list of lists) for (const id of list) expect(ids.has(id)).toBe(true);
  });

  it("tell the record in order, one state per step", () => {
    const only = (lists: StepId[][], id: StepId) => lists.filter((list) => list.includes(id)).length;
    for (const item of STEPS) {
      expect(only([PRINTER.before, PRINTER.after], item.id)).toBe(1);
      expect(only([PRINTER.printing, PRINTER.paused], item.id)).toBe(1);
      expect(only([CAMERA.lifting, CAMERA.loose], item.id)).toBe(1);
    }
    expect(PRINTER.after[0]).toBe("warm");
    expect(PRINTER.paused[0]).toBe("pause");
    expect(CAMERA.loose[0]).toBe("loose");
    expect(index("warm")).toBeLessThan(index("hot"));
    expect(index("hot")).toBeLessThan(index("loose"));
    expect(index("loose")).toBeLessThan(index("pause"));
    expect(index("pause")).toBeLessThan(index("cancel"));
  });

  it("draw each message inside its own step, leaving before the next one draws", () => {
    for (const fill of FILLS) {
      const owner = PLACED[stepAt(fill.at)];
      expect(fill.at + fill.d).toBeLessThanOrEqual(owner.to);
      expect(fill.out).toBe(owner.to);
    }
    const lanes = new Map<string, typeof FILLS>();
    for (const fill of FILLS) {
      const key = `${fill.wire} ${fill.lane === "send" || fill.lane === "look" ? "out" : "back"}`;
      lanes.set(key, [...(lanes.get(key) ?? []), fill]);
    }
    for (const fills of lanes.values()) {
      const sorted = [...fills].sort((a, b) => a.at - b.at);
      for (let i = 1; i < sorted.length; i++) expect(sorted[i - 1].out).toBeLessThanOrEqual(sorted[i].at);
    }
  });
});

describe("the story's words and numbers", () => {
  const facts = storyFacts();
  const record = fresh();
  const look = byId(record, IDS.look);
  const bed = byId(record, IDS.bed);
  const nozzle = byId(record, IDS.nozzle);
  const pause = byId(record, IDS.pause);
  const cancel = byId(record, IDS.cancel);
  const printer = readDeviceFile();

  it("come from the recorded scenario", () => {
    expect(facts.look.method).toBe(look.request.method);
    expect(facts.camera.id).toBe(look.request.params.device);
    expect(facts.bed.target).toBe(bed.request.params.channel);
    expect(facts.bed.value).toBe(quantity(bed));
    expect(facts.bed.status).toBe(bed.result!.status);
    expect(facts.bed.note).toBe(bed.before);
    expect(facts.nozzle.value).toBe(quantity(nozzle));
    expect(facts.nozzle.refusal.name).toBe(nozzle.error!.data.name);
    expect(facts.nozzle.refusal.code).toBe(nozzle.error!.code);
    expect(facts.nozzle.refusal.reason).toBe(humane(nozzle.error!.message.slice(0, nozzle.error!.message.indexOf(" ("))));
    expect(facts.pause.target).toBe(pause.request.params.action);
    expect(facts.pause.status).toBe(pause.result!.status);
    expect(facts.cancel.target).toBe(cancel.request.params.action);
    expect(facts.cancel.status).toBe("pending");
    expect(facts.requests).toBe(record.record.exchanges.length);
    const described = record.record.devices!.find((item) => item.id === bed.request.params.device)!;
    expect(facts.file).toBe(described.file);
    expect(facts.printer.driver).toBe(described.driver);
    expect(facts.camera.driver).toBe(record.record.devices!.find((item) => item.id === look.request.params.device)!.driver);
    expect(facts.confirmed).toBe(`confirmed by ${described.confirmed.by} ${described.confirmed.at}`);
    expect([facts.bed.before, facts.bed.after]).toEqual([(bed as any)[facts.bed.channel].before.value, (bed as any)[facts.bed.channel].after.value]);
    expect(facts.camera.image).toBe(`${look.result!.value.mimeType} ${look.result!.value.width} × ${look.result!.value.height}`);
  });

  it("show the kernel's checks and verdict in the record's words", () => {
    for (const item of PLACED) {
      const view = facts.kernel[item.id];
      if (!TOLD[item.id]) {
        expect(view.verdict.text).toBe("Waiting for a command");
        continue;
      }
      const kernel = (byId(record, IDS[TOLD[item.id]!]) as Record<string, any>).kernel;
      for (const [name, word] of Object.entries(kernel.checks as Record<string, string>)) expect(view.checks).toContainEqual({ name: `${name[0].toUpperCase()}${name.slice(1)}`, word });
      if (view.reading) {
        expect(view.checks).toContainEqual({ name: "Grant", word: kernel.grant });
        expect(view.checks).toContainEqual({ name: "Audit log", word: `entry ${kernel.logged.join(", ")}` });
        expect(view.verdict).toEqual({ kind: "granted", text: "allowed" });
      }
    }
    expect(facts.kernel.warm.verdict.text).toBe("granted");
    expect(facts.kernel.hot.verdict).toEqual({ kind: "blocked", text: nozzle.error!.data.name });
    expect(facts.kernel.cancel.verdict).toEqual({ kind: "confirm", text: "confirmation required" });
  });

  it("take the limits from printer.hal.yaml, which match what the hub described", () => {
    const limits = record.record.devices!.find((item) => item.id === printer.id)!.limits;
    for (const channel of [facts.nozzle.channel, facts.bed.channel]) {
      expect(limits[channel].max.value).toBe(printer.write[channel].max);
      expect(limits[channel].max.unit).toBe(printer.write[channel].unit);
    }
    expect(facts.nozzle.max).toBe(amount(printer.write[facts.nozzle.channel].max, printer.write[facts.nozzle.channel].unit));
    expect(facts.bed.max).toBe(amount(printer.write[facts.bed.channel].max, printer.write[facts.bed.channel].unit));
    expect(facts.printer.driver).toBe("moonraker");
    expect(facts.camera.driver).toBe("http");
    expect(printer.actions[facts.cancel.target]).toMatchObject({ confirm: expect.any(String) });
  });

  it("follow the record when it changes", () => {
    const changed = fresh();
    byId(changed, IDS.nozzle).request.params.value = 290;
    const warmed = byId(changed, IDS.bed);
    warmed.request.params.value = 75;
    (warmed as Record<string, any>)[warmed.request.params.channel].after.value = 75;
    const other = storyFacts(changed, readDeviceFile());
    expect(other.nozzle.value).toBe("290 °C");
    expect(storyLines(other).hot).toContain(nb("290 °C"));
    expect(other.bed.value).toBe("75 °C");
    expect(storyLines(other).warm).toContain(nb("75 °C"));
    expect(JSON.stringify(storyTrace(other).hot)).toContain(nb("290 °C"));
  });

  it("follow the device file when a person changes a limit", () => {
    const tighter = readDeviceFile();
    tighter.write[facts.nozzle.channel].max = 250;
    expect(storyLines(storyFacts(fresh(), tighter)).hot).toContain(nb("250 °C"));
  });

  it("give every counted step a trace line in the record's words", () => {
    const trace = storyTrace(facts);
    for (const item of COUNTED) expect(trace[item.id]?.length).toBeGreaterThan(0);
    expect(trace.hot).toContainEqual({ kind: "error", code: nozzle.error!.code, name: nozzle.error!.data.name, reason: nb(facts.nozzle.refusal.reason) });
    expect(trace.cancel).toContainEqual({ kind: "result", text: "pending" });
  });

  it("read as short plain sentences that follow the copy rules", () => {
    for (const line of Object.values(storyLines(facts))) {
      expect(line).toMatch(/[.]$/);
      expect(line).not.toMatch(/[;:!–—]/);
      expect(line).not.toMatch(/\bAI\b/);
      expect(line.split(/\s+/).length).toBeLessThanOrEqual(16);
    }
    expect(nb("warm to 70 °C")).toBe("warm to 70 °C");
    expect(humane("extruder_target 300 degC exceeds the limit of 260 degC")).toBe("extruder_target 300 °C exceeds the limit of 260 °C");
  });
});
