import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { amount, humane, nb, readDeviceFile, storyFacts, storyLines } from "../../src/lib/story/facts";
import { ALWAYS, NEVER, TOTAL } from "../../src/lib/story/script";
import { CAMERA, CLIENT, DRIVER, FILLS, HUB, KERNEL, NOTE_AT, PRINTER, SNAP_AT, TITLE_OUT, type Span } from "../../src/lib/story/timeline";
import type { Exchange, Scenario } from "../../src/lib/scenario";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = readFileSync(scenarioFile, "utf8");
const fresh = () => scenarioFrom(recorded) as Scenario;
const spans = (items: Span[]) => items.flatMap((item) => [item.at, item.out]);

function exchangesOf(scenario: Scenario) {
  const all = scenario.record.exchanges;
  const writes = all.filter((exchange) => exchange.request.method === "hal/write");
  const actions = all.filter((exchange) => exchange.request.method === "hal/action");
  return {
    look: all.find((exchange) => exchange.request.method === "hal/read")!,
    bed: writes.find((exchange) => exchange.result)!,
    nozzle: writes.find((exchange) => exchange.error)!,
    pause: actions.find((exchange) => exchange.result?.status === "done")!,
    cancel: actions.find((exchange) => exchange.result?.status === "pending")!,
  };
}

const quantity = (exchange: Exchange) => amount(exchange.request.params.value, exchange.request.params.unit);

describe("the story's timeline", () => {
  it("places every cue inside the story", () => {
    const passes = [KERNEL.bed, KERNEL.nozzle, KERNEL.pause, KERNEL.cancel];
    const points: number[] = [
      TITLE_OUT,
      ...Object.values(NOTE_AT),
      ...Object.values(SNAP_AT),
      ...spans([...CLIENT.asks, ...CLIENT.hears, ...Object.values(HUB)]),
      ...passes.flatMap((pass) => spans([...pass.checks.map((check) => check.span), pass.verdict])),
      ...spans([...DRIVER.waiting, DRIVER.bed, DRIVER.pause, ...DRIVER.sent, ...DRIVER.moonraker, ...DRIVER.http]),
      ...spans([PRINTER.printing, PRINTER.paused, ...Object.values(CAMERA)]),
      PRINTER.bed.at,
      PRINTER.bed.at + PRINTER.bed.d,
      ...FILLS.flatMap((fill) => [fill.at, fill.at + fill.d, fill.out]),
    ].filter((point) => point !== ALWAYS && point !== NEVER);
    for (const point of points) {
      expect(point).toBeGreaterThanOrEqual(0);
      expect(point).toBeLessThanOrEqual(TOTAL);
    }
  });

  it("tells the scenario in order", () => {
    const times = Object.values(NOTE_AT);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(CAMERA.corner.at).toBeLessThan(KERNEL.bed.verdict.at);
    expect(KERNEL.bed.verdict.at).toBeLessThan(DRIVER.bed.at);
    expect(DRIVER.bed.at).toBeLessThan(PRINTER.bed.at);
    expect(PRINTER.bed.at + PRINTER.bed.d).toBeLessThan(KERNEL.nozzle.verdict.at);
    expect(KERNEL.nozzle.verdict.at).toBeLessThan(CAMERA.loose.at);
    expect(CAMERA.loose.at).toBeLessThan(KERNEL.pause.verdict.at);
    expect(KERNEL.pause.verdict.at).toBeLessThanOrEqual(DRIVER.pause.at);
    expect(DRIVER.pause.at).toBeLessThan(PRINTER.paused.at);
    expect(PRINTER.paused.at).toBeLessThan(KERNEL.cancel.verdict.at);
    expect(KERNEL.cancel.verdict.at).toBeLessThan(HUB.asked.at);
  });

  it("lets each piece on a lane leave before the next one arrives", () => {
    const lanes = new Map<string, typeof FILLS>();
    for (const fill of FILLS) {
      const key = `${fill.wire} ${fill.lane === "send" || fill.lane === "look" ? "out" : "back"}`;
      lanes.set(key, [...(lanes.get(key) ?? []), fill]);
    }
    for (const fills of lanes.values()) {
      const sorted = [...fills].sort((a, b) => a.at - b.at);
      for (let index = 1; index < sorted.length; index++) expect(sorted[index - 1].out).toBeLessThanOrEqual(sorted[index].at);
    }
    for (const group of [CLIENT.asks, CLIENT.hears, DRIVER.waiting]) {
      for (let index = 1; index < group.length; index++) expect(group[index - 1].out).toBeLessThanOrEqual(group[index].at);
    }
  });
});

describe("the story's words and numbers", () => {
  const facts = storyFacts();
  const { look, bed, nozzle, pause, cancel } = exchangesOf(fresh());
  const printer = readDeviceFile();

  it("come from the recorded scenario", () => {
    expect(facts.look.method).toBe(look.request.method);
    expect(facts.camera.id).toBe(look.request.params.device);
    expect(facts.bed.method).toBe(bed.request.method);
    expect(facts.bed.target).toBe(bed.request.params.channel);
    expect(facts.bed.value).toBe(quantity(bed));
    expect(facts.bed.status).toBe(bed.result!.status);
    expect(facts.nozzle.value).toBe(quantity(nozzle));
    expect(facts.nozzle.refusal.name).toBe(nozzle.error!.data.name);
    expect(facts.nozzle.refusal.code).toBe(nozzle.error!.code);
    expect(facts.nozzle.refusal.reason).toBe(humane(nozzle.error!.message.slice(0, nozzle.error!.message.indexOf(" ("))));
    expect(facts.pause.target).toBe(pause.request.params.action);
    expect(facts.pause.status).toBe(pause.result!.status);
    expect(facts.cancel.target).toBe(cancel.request.params.action);
    expect(facts.cancel.status).toBe("pending");
    const described = fresh().record.devices!.find((item) => item.id === bed.request.params.device)!;
    expect(facts.file).toBe(described.file);
    expect(facts.printer.driver).toBe(described.driver);
    expect(facts.camera.driver).toBe(fresh().record.devices!.find((item) => item.id === look.request.params.device)!.driver);
    expect(facts.confirmed).toBe(`confirmed by ${described.confirmed.by} ${described.confirmed.at}`);
    expect([facts.bed.before, facts.bed.after]).toEqual([(bed as any)[facts.bed.channel].before.value, (bed as any)[facts.bed.channel].after.value]);
    expect(facts.camera.image).toBe(`${look.result!.value.mimeType} ${look.result!.value.width} × ${look.result!.value.height}`);
  });

  it("take the limits from printer.hal.yaml, which match what the hub described", () => {
    const limits = fresh().record.devices!.find((item) => item.id === printer.id)!.limits;
    for (const channel of [facts.nozzle.channel, facts.bed.channel]) {
      expect(limits[channel].max.value).toBe(printer.write[channel].max);
      expect(limits[channel].max.unit).toBe(printer.write[channel].unit);
    }
    expect(facts.printer.id).toBe(printer.id);
    expect(facts.nozzle.max).toBe(amount(printer.write[facts.nozzle.channel].max, printer.write[facts.nozzle.channel].unit));
    expect(facts.bed.max).toBe(amount(printer.write[facts.bed.channel].max, printer.write[facts.bed.channel].unit));
    expect(facts.printer.driver).toBe("moonraker");
    expect(facts.camera.driver).toBe("http");
    expect(printer.actions[facts.cancel.target]).toMatchObject({ confirm: expect.any(String) });
  });

  it("follow the record when it changes", () => {
    const changed = fresh();
    const moved = exchangesOf(changed);
    moved.nozzle.request.params.value = 290;
    moved.bed.request.params.value = 75;
    (moved.bed as Record<string, any>)[moved.bed.request.params.channel].after.value = 75;
    const other = storyFacts(changed, readDeviceFile());
    expect(other.nozzle.value).toBe("290 °C");
    expect(storyLines(other).hot).toContain(nb("290 °C"));
    expect(other.bed.value).toBe("75 °C");
    expect(storyLines(other).heat).toContain(nb("75 °C"));
  });

  it("follow the device file when a person changes a limit", () => {
    const tighter = readDeviceFile();
    tighter.write[facts.nozzle.channel].max = 250;
    expect(storyLines(storyFacts(fresh(), tighter)).hot).toContain(nb("250 °C"));
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
