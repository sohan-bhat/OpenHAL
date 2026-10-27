import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { IDS, TOLD, amount, humane, nb, named, readDeviceFile, storyFacts, storyLines, storyTrace } from "../../src/lib/story/facts";
import { COUNTED, PLACED, STEPS, TOTAL, step, stepAt, type StepId } from "../../src/lib/story/script";
import { AGENT, CAMERA, DRIVER, FILLS, HUB, TRIPS, WIRES, stations } from "../../src/lib/story/timeline";
import type { Exchange, Scenario } from "../../src/lib/scenario";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = readFileSync(scenarioFile, "utf8");
const fresh = () => scenarioFrom(recorded) as Scenario;
const byId = (scenario: Scenario, id: string) => scenario.record.exchanges.find((exchange) => exchange.id === id)!;
const quantity = (exchange: Exchange) => amount(exchange.request.params.value, exchange.request.params.unit);
const index = (id: StepId) => step(id).index;
const told = (scenario: Scenario, id: StepId) => byId(scenario, IDS[TOLD[id]!]) as Exchange & Record<string, any>;

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
    const lists = [AGENT.person, ...Object.values(AGENT.asks), ...Object.values(AGENT.hears), ...Object.values(HUB), ...Object.values(DRIVER), ...Object.values(CAMERA), ...Object.values(WIRES), TRIPS.map((trip) => trip.id)];
    for (const list of lists) for (const id of list) expect(ids.has(id)).toBe(true);
  });

  it("light every station a message passes, the hub on every request", () => {
    for (const trip of TRIPS) expect([...step(trip.id).lit].sort(), trip.id).toEqual(stations(trip).sort());
    for (const item of PLACED.filter((entry) => TOLD[entry.id])) {
      expect(TRIPS.map((trip) => trip.id)).toContain(item.id);
      expect(item.lit).toContain("hub");
      expect(item.lit).toContain("kernel");
    }
    expect(step("ask").lit).toEqual(["client"]);
    expect([...step("end").lit].sort()).toEqual(["camera", "client", "driver", "hub", "kernel", "printer"]);
  });

  it("take each message as far as the record says it went", () => {
    const record = fresh();
    for (const trip of TRIPS) {
      const exchange = told(record, trip.id);
      const reading = exchange.request.method === "hal/read";
      expect(trip.out === "look", trip.id).toBe(reading);
      expect(trip.wires.includes(4), trip.id).toBe(reading || (exchange.printer_received ?? []).length > 0);
      expect(trip.wires[0] === 1, trip.id).toBe(String(exchange.by).startsWith("agent:"));
      expect(trip.back === "blocked", trip.id).toBe(Boolean(exchange.error));
      expect(trip.back === "pending", trip.id).toBe(exchange.result?.status === "pending");
    }
  });

  it("show a read passing the kernel with no grant, and a driver waiting only for commands", () => {
    const record = fresh();
    for (const id of DRIVER.frame) {
      expect(told(record, id).request.method).toBe("hal/read");
      expect(told(record, id).kernel.grant).toBe("not needed");
      expect(DRIVER.waiting).not.toContain(id);
    }
    for (const id of [...DRIVER.bed, ...DRIVER.pause, ...DRIVER.cancel]) expect(told(record, id).kernel.grant).toBe("issued");
    for (const id of DRIVER.waiting) expect(TOLD[id] ? told(record, id).kernel.grant : "none").toBe("none");
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

  it("tell the record in order", () => {
    const order = PLACED.filter((item) => TOLD[item.id]).map((item) => IDS[TOLD[item.id]!]);
    expect(order).toEqual(fresh().record.exchanges.map((exchange) => exchange.id));
    expect(index("warm")).toBeLessThan(index("hot"));
    expect(index("cancel")).toBeLessThan(index("approve"));
    expect(index("approve")).toBeLessThan(index("end"));
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
  const approve = byId(record, IDS.approve) as Exchange & Record<string, any>;
  const audit = (record.record as Record<string, any>).audit;
  const printer = readDeviceFile();

  it("come from the recorded scenario", () => {
    expect(facts.look.method).toBe(look.request.method);
    expect(facts.camera.id).toBe(look.request.params.device);
    expect(facts.bed.target).toBe(bed.request.params.channel);
    expect(facts.bed.value).toBe(quantity(bed));
    expect(facts.bed.status).toBe(bed.result!.status);
    expect(facts.bed.note).toBe(bed.before);
    expect(facts.nozzle.value).toBe(quantity(nozzle));
    expect(facts.nozzle.note).toBe(nozzle.before);
    expect(facts.nozzle.refusal.name).toBe(nozzle.error!.data.name);
    expect(facts.nozzle.refusal.code).toBe(nozzle.error!.code);
    expect(facts.nozzle.refusal.reason).toBe(humane(nozzle.error!.message.slice(0, nozzle.error!.message.indexOf(" ("))));
    expect(facts.pause.target).toBe(pause.request.params.action);
    expect(facts.pause.status).toBe(pause.result!.status);
    expect(facts.cancel.target).toBe(cancel.request.params.action);
    expect(facts.cancel.status).toBe(cancel.result!.status);
    expect(facts.approve.method).toBe(approve.request.method);
    expect(facts.approve.status).toBe(approve.result!.status);
    expect(`action:${facts.approve.target}`).toBe(approve.result!.target);
    expect(facts.approve.approved).toBe(`approved by ${named(approve.kernel.approved_by)}`);
    expect(facts.approve.note).toBe(approve.before);
    const described = record.record.devices!.find((item) => item.id === bed.request.params.device)!;
    expect(facts.file).toBe(described.file);
    expect(facts.printer.driver).toBe(described.driver);
    expect(facts.camera.driver).toBe(record.record.devices!.find((item) => item.id === look.request.params.device)!.driver);
    expect(facts.confirmed).toBe(`confirmed by ${described.confirmed.by} ${described.confirmed.at}`);
    expect([facts.bed.before, facts.bed.after]).toEqual([(bed as any)[facts.bed.channel].before.value, (bed as any)[facts.bed.channel].after.value]);
    expect(facts.camera.image).toBe(`${look.result!.value.mimeType} ${look.result!.value.width}\u00a0×\u00a0${look.result!.value.height}`);
  });

  it("show the printer as the hub saw it after each step's request", () => {
    const [nozzleRow, bedRow, stateRow] = facts.printer.readings;
    for (const item of PLACED.filter((entry) => TOLD[entry.id])) {
      const view = told(record, item.id).printer;
      expect(nozzleRow.at[item.id]).toBe(amount(view.extruder_temp.value, view.extruder_temp.unit));
      expect(bedRow.at[item.id]).toBe(amount(view.bed_target.value, view.bed_target.unit));
      expect(stateRow.at[item.id]).toBe(view.state);
    }
    expect(stateRow.at.approve).toBe("cancelled");
    expect(stateRow.at.end).toBe(stateRow.at.approve);
    expect(bedRow.at.ask).toBe(bedRow.at.look);
  });

  it("show the kernel's checks and grant in the record's words", () => {
    for (const item of PLACED) {
      const view = facts.kernel[item.id];
      if (!TOLD[item.id]) {
        expect(view.verdict.text).toBe("Waiting for a command");
        continue;
      }
      const kernel = told(record, item.id).kernel;
      for (const [name, word] of Object.entries(kernel.checks as Record<string, string>)) expect(view.checks).toContainEqual({ name: `${name[0].toUpperCase()}${name.slice(1)}`, word });
      if (view.reading) {
        expect(view.checks).toContainEqual({ name: "Grant", word: kernel.grant });
        expect(view.checks).toContainEqual({ name: "Audit log", word: `entry ${kernel.logged.join(", ")}` });
        expect(view.verdict).toEqual({ kind: "granted", text: "allowed" });
      }
    }
    expect(facts.kernel.hot.verdict).toEqual({ kind: "blocked", text: nozzle.error!.data.name });
    expect(facts.kernel.cancel.verdict).toEqual({ kind: "confirm", text: "confirmation required" });
    expect(facts.kernel.approve.checks.find((check) => check.name === "Confirmation")!.word).toBe("ok");
    expect(facts.kernel.approve.verdict.text).toBe("granted");
  });

  it("end on the audit log's counts", () => {
    expect(facts.audit.counts).toBe(`${audit.counts.requests} requests, ${audit.counts.refused} refused, ${audit.counts.confirmed_by_a_person} confirmed by a person`);
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
    byId(changed, IDS.nozzle).before = "a hotter nozzle might help";
    const warmed = byId(changed, IDS.bed);
    warmed.request.params.value = 75;
    (warmed as Record<string, any>)[warmed.request.params.channel].after.value = 75;
    const approved = byId(changed, IDS.approve) as Record<string, any>;
    approved.kernel.approved_by = "human:alex";
    approved.printer.state = "standby";
    approved.printer.extruder_temp.value = 30;
    const counts = (changed.record as Record<string, any>).audit.counts;
    counts.requests = 9;
    (byId(changed, IDS.look) as Record<string, any>).kernel.logged = [41];
    const other = storyFacts(changed, readDeviceFile());
    expect(other.nozzle.value).toBe("290 °C");
    expect(storyLines(other).hot).toContain(nb("290 °C"));
    expect(storyTrace(other).hot).toContainEqual({ kind: "note", text: "a hotter nozzle might help" });
    expect(other.bed.value).toBe("75 °C");
    expect(storyLines(other).warm).toContain(nb("75 °C"));
    expect(JSON.stringify(storyTrace(other).hot)).toContain(nb("290 °C"));
    expect(other.approve.approved).toBe("approved by alex");
    expect(other.printer.readings[2].at.approve).toBe("standby");
    expect(storyLines(other).approve).toContain("standby");
    expect(other.printer.readings[0].at.end).toBe("30 °C");
    expect(other.audit.counts).toMatch(/^9 requests/);
    expect(other.kernel.look.checks).toContainEqual({ name: "Audit log", word: "entry 41" });
  });

  it("follow the device file when a person changes a limit", () => {
    const tighter = readDeviceFile();
    tighter.write[facts.nozzle.channel].max = 250;
    expect(storyLines(storyFacts(fresh(), tighter)).hot).toContain(nb("250 °C"));
  });

  it("give every counted step a trace in the record's words, each result in its outcome's color", () => {
    const trace = storyTrace(facts);
    for (const item of COUNTED) expect(trace[item.id]?.length).toBeGreaterThan(0);
    for (const item of PLACED.filter((entry) => TOLD[entry.id])) expect(trace[item.id]![0]).toEqual({ kind: "note", text: told(record, item.id).before });
    expect(trace.hot).toContainEqual({ kind: "error", code: nozzle.error!.code, name: nozzle.error!.data.name, reason: nb(facts.nozzle.refusal.reason) });
    expect(trace.cancel).toContainEqual({ kind: "result", text: "pending", tone: "pending" });
    expect(trace.warm).toContainEqual({ kind: "result", text: "done", tone: "ok" });
    expect(trace.approve).toContainEqual({ kind: "request", method: "hal/confirmations/approve", text: `${facts.approve.target} on ${facts.approve.device}` });
    expect(trace.end).toEqual([{ kind: "note", text: facts.audit.counts }]);
  });

  it("read as short plain sentences that follow the copy rules", () => {
    for (const line of Object.values(storyLines(facts))) {
      expect(line).toMatch(/[.]$/);
      expect(line).not.toMatch(/[;:!–—]/);
      expect(line).not.toMatch(/\bAI\b/);
      expect(line).not.toMatch(/\b(it|them|they|that's)\b/i);
      expect(line).not.toMatch(/\bonly\b|morning|wake/i);
      expect(line.split(/\s+/).length).toBeLessThanOrEqual(16);
    }
    expect(nb("warm to 70 °C")).toBe("warm to 70\u00a0°C");
    expect(humane("extruder_target 300 degC exceeds the limit of 260 degC")).toBe("extruder_target 300 °C exceeds the limit of 260 °C");
  });
});
