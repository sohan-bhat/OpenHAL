import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ASKED, IDS, LIFELINES, TOLD, amount, humane, nb, named, readDeviceFile, storyFacts, storyLines, type Lifeline, type Sending } from "../../src/lib/story/facts";
import { COUNTED, NEVER, PLACED, STEPS, TOTAL, during, step, stepAt, type StepId } from "../../src/lib/story/script";
import { SEEN, drawing, storySequence } from "../../src/lib/story/timeline";
import type { Exchange, Scenario } from "../../src/lib/scenario";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = readFileSync(scenarioFile, "utf8");
const fresh = () => scenarioFrom(recorded) as Scenario;
const byId = (scenario: Scenario, id: string) => scenario.record.exchanges.find((exchange) => exchange.id === id)! as Exchange & Record<string, any>;
const quantity = (exchange: Exchange) => amount(exchange.request.params.value, exchange.request.params.unit);
const told = (scenario: Scenario, id: StepId) => byId(scenario, IDS[TOLD[id]!]);
const sending = COUNTED.filter((item) => item.id !== "end").map((item) => item.id as Sending);
const at = (spans: ReadonlyArray<readonly [number, number]>, t: number) => spans.some(([start, end]) => t >= start && t < end);

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

  it("tell the record in order", () => {
    const order = PLACED.filter((item) => TOLD[item.id]).map((item) => IDS[TOLD[item.id]!]);
    expect(order).toEqual(fresh().record.exchanges.map((exchange) => exchange.id));
  });

  it("mark each piece for the first frame and for the static story", () => {
    expect(during([[0, 20]])).toEqual({ "data-in": "0 20", "data-on": "", "data-end": undefined });
    expect(during([[300, NEVER]])).toEqual({ "data-in": `300 ${NEVER}`, "data-on": undefined, "data-end": "" });
  });
});

describe("the sequence diagram", () => {
  const facts = storyFacts();
  const sequence = storySequence(facts);
  const record = fresh();
  const row = (id: Sending) => sequence.rows.find((item) => item.id === id)!;

  it("has one row for every step that sends something, in story order", () => {
    expect(sequence.rows.map((item) => item.id)).toEqual(sending);
  });

  it("takes each request as far as the record says it went", () => {
    for (const id of sending.filter((item) => TOLD[item])) {
      const exchange = told(record, id);
      const said = facts.said[id];
      const last = said[said.length - 1];
      const stopped = Boolean(exchange.error) || exchange.result?.status === "pending";
      expect(last.to, id).toBe(stopped ? "hub" : "printer");
      expect(said[0].from, id).toBe(String(exchange.by).startsWith("human:") ? "owner" : "agent");
      expect(row(id).legs[0].to, id).toBe(said[0].from === "agent" || said[0].from === "owner" ? "hub" : said[0].to);
      expect(row(id).legs.at(-1)!.to, id).toBe(last.to);
      expect(last.answer!.text, id).toBe(exchange.error ? exchange.error.data.name : String(exchange.result?.status ?? "done"));
      expect(last.answer!.tone, id).toBe(exchange.error ? "blocked" : exchange.result?.status === "pending" ? "confirm" : "ok");
    }
    expect(facts.said.ask).toEqual([{ from: "owner", to: "agent", label: ASKED }]);
  });

  it("puts the lifelines in the owner's order and draws each leg toward its receiver, the hub on the way to the printer", () => {
    const place = (name: Lifeline) => LIFELINES.indexOf(name);
    expect(LIFELINES).toEqual(["agent", "owner", "hub", "printer"]);
    for (const item of sequence.rows) {
      for (const leg of [...item.legs, ...(item.reply ? [item.reply.leg] : [])]) {
        const where = `${item.id} ${leg.from} to ${leg.to}`;
        const [left, right] = [Math.min(place(leg.from), place(leg.to)), Math.max(place(leg.from), place(leg.to))];
        expect(leg.back, where).toBe(place(leg.to) < place(leg.from));
        expect(left < place("agent") && place("agent") < right, where).toBe(false);
        if (left < place("owner") && place("owner") < right) expect(leg.over, where).toBeCloseTo((place("owner") - left) / (right - left), 3);
        else expect(leg.over, where).toBeUndefined();
      }
      for (const leg of item.legs.filter((entry) => entry.to === "printer")) expect(leg.from).toBe("hub");
    }
    expect(row("ask").legs.map((leg) => [leg.from, leg.to, leg.back])).toEqual([["owner", "agent", true]]);
    expect(row("warm").legs[0].over).toBe(0.5);
  });

  it("answers every request with a dashed reply from where the request stopped back to the lifeline that sent it", () => {
    for (const item of sequence.rows) {
      const said = facts.said[item.id];
      const answer = said[said.length - 1].answer;
      if (!answer) {
        expect(item.reply, item.id).toBeUndefined();
        continue;
      }
      expect(item.reply!.answer, item.id).toEqual(answer);
      expect(item.reply!.from, item.id).toBe(item.legs[item.legs.length - 1].to);
      expect(item.reply!.to, item.id).toBe(said[0].from);
      expect(item.reply!.leg.back, item.id).toBe(true);
    }
    expect(row("hot").reply).toMatchObject({ from: "hub", to: "agent", answer: { tone: "blocked" } });
    expect(row("cancel").reply).toMatchObject({ from: "hub", to: "agent", answer: { text: "pending", tone: "confirm" } });
    expect(row("ask").reply).toBeUndefined();
  });

  it("shows a row's label first, then draws its legs one after another, then its answer and the reply, all inside its own step", () => {
    for (const item of sequence.rows) {
      const { from, to } = step(item.id);
      expect(item.words[0].shows).toBeGreaterThanOrEqual(from);
      for (const [index, leg] of item.legs.entries()) {
        expect(leg.lands).toBe(leg.at + leg.d);
        if (index > 0) expect(leg.at).toBeGreaterThan(item.legs[index - 1].lands);
      }
      expect(item.legs[0].at).toBeGreaterThan(item.words[0].shows);
      expect(item.live[0]).toBe(item.words[0].shows);
      expect(item.lands).toBeLessThan(to);
      if (!item.reply) continue;
      expect(item.reply.shows, item.id).toBeGreaterThan(item.lands);
      expect(item.reply.leg.at, item.id).toBe(item.reply.shows);
      expect(item.reply.leg.lands, item.id).toBe(item.reply.leg.at + item.reply.leg.d);
      expect(item.reply.leg.lands, item.id).toBeLessThan(to);
    }
  });

  it("holds the pending request at the hub until the owner's approval lands there", () => {
    const cancel = row("cancel");
    const approve = row("approve");
    expect(cancel.held).toEqual([cancel.lands, approve.legs[0].lands]);
    expect(cancel.live).toEqual([cancel.words[0].shows, step("cancel").to]);
    expect(drawing(cancel)).toEqual([cancel.live[0], cancel.lands]);
    expect(drawing(approve)).toEqual(approve.live);
    expect(approve.legs[0].from).toBe("owner");
    expect(approve.legs[1].at).toBeGreaterThan(approve.legs[0].lands);
    expect(sequence.rows.filter((item) => item.held).map((item) => item.id)).toEqual(["cancel"]);
  });

  it("changes the printer's readings when the request that changed them lands", () => {
    const value = (name: string, t: number) => sequence.readings.find((reading) => reading.name === name)!.values.find((entry) => at(entry.spans, t))!.text;
    const reading = (name: string, id: StepId) => facts.printer.readings.find((entry) => entry.name === name)!.at[id];
    expect(value("Bed target", row("warm").lands)).toBe(reading("Bed target", "look"));
    expect(value("Bed target", row("warm").lands + 1)).toBe(reading("Bed target", "warm"));
    expect(value("State", row("pause").lands + 1)).toBe(reading("State", "pause"));
    expect(value("State", row("approve").lands)).toBe(reading("State", "cancel"));
    expect(value("State", TOTAL)).toBe(reading("State", "end"));
    expect(value("Nozzle", TOTAL)).toBe(reading("Nozzle", "end"));
    for (const entry of sequence.readings) {
      for (let t = 0; t < TOTAL; t += 0.5) expect(entry.values.filter((item) => at(item.spans, t)).length, `${entry.name} at ${t}`).toBe(1);
    }
  });

  it("shows the approval's readings as the cancel lands, then the nozzle cooling, and drops the stale target", () => {
    const value = (name: string, t: number) => sequence.readings.find((reading) => reading.name === name)!.values.find((entry) => at(entry.spans, t))!.text;
    const reading = (name: string, id: StepId) => facts.printer.readings.find((entry) => entry.name === name)!.at[id];
    const approve = row("approve");
    expect(value("Nozzle", approve.lands)).toBe(reading("Nozzle", "cancel"));
    expect(value("Nozzle", approve.lands + 1)).toBe(reading("Nozzle", "approve"));
    expect(value("Nozzle", approve.reply!.leg.lands + 1)).toBe(facts.printer.readings[0].cooling[0]);
    expect(approve.reply!.leg.lands + 1).toBeLessThan(step("approve").to);
    expect(value("Nozzle", step("end").from)).toBe(reading("Nozzle", "end"));
    expect(value("State", approve.lands + 1)).toBe(reading("State", "approve"));
    expect(sequence.readings.map((entry) => entry.shown)).toEqual([undefined, [[0, approve.lands + 1]], undefined]);
  });

  it("shows the frame each read returned from the moment the read lands, and marks what the agent noticed", () => {
    const look = row("look");
    const loose = row("loose");
    expect(sequence.frames.printing).toEqual([[0, look.lands + 1]]);
    expect(sequence.frames.lifting).toEqual([[look.lands + 1, loose.lands + 1]]);
    expect(sequence.frames.loose).toEqual([[loose.lands + 1, NEVER]]);
    expect(sequence.seen.lifting).toEqual([[look.lands + 1, step("look").to]]);
    expect(sequence.seen.loose).toEqual([[loose.lands + 1, step("loose").to]]);
    expect(sequence.notes).toEqual({ lifting: [[look.lands + 1, loose.lands + 1]], loose: [[loose.lands + 1, NEVER]] });
    expect(SEEN).toEqual({ lifting: "Seen: first layer corner lifting", loose: "Seen: print loose" });
    for (const id of ["look", "warm", "hot"] as const) expect(at(sequence.notes.lifting, step(id).to - 1), id).toBe(true);
    for (const id of ["pause", "cancel", "approve", "end"] as const) expect(at(sequence.notes.loose, step(id).from), id).toBe(true);
    expect(at([...sequence.notes.lifting, ...sequence.notes.loose], step("ask").to - 1)).toBe(false);
  });
});

describe("the story's words and numbers", () => {
  const facts = storyFacts();
  const record = fresh();
  const bed = byId(record, IDS.bed);
  const nozzle = byId(record, IDS.nozzle);
  const pause = byId(record, IDS.pause);
  const cancel = byId(record, IDS.cancel);
  const approve = byId(record, IDS.approve);
  const audit = (record.record as Record<string, any>).audit;
  const printer = readDeviceFile();

  it("come from the recorded scenario", () => {
    expect(facts.said.look[0].label).toBe(`read ${byId(record, IDS.look).request.params.channel}`);
    expect(facts.said.warm[0].label).toBe(nb(`${bed.request.params.channel} ${quantity(bed)}`));
    expect(facts.said.hot[0].label).toBe(nb(`${nozzle.request.params.channel} ${quantity(nozzle)}`));
    expect(facts.said.pause[0].label).toBe(pause.request.params.action);
    expect(facts.said.cancel[0].label).toBe(cancel.request.params.action);
    expect(facts.said.approve.map((said) => said.label)).toEqual([approve.request.method.split("/").pop(), String(approve.result!.target).split(":")[1]]);
    expect(facts.nozzle.refusal.name).toBe(nozzle.error!.data.name);
    expect(facts.nozzle.refusal.code).toBe(nozzle.error!.code);
    expect(facts.nozzle.refusal.reason).toBe(humane(nozzle.error!.message.slice(0, nozzle.error!.message.indexOf(" ("))));
    expect(facts.cancel.status).toBe(cancel.result!.status);
    expect(facts.approve.approved).toBe(`approved by ${named(approve.kernel.approved_by)}`);
    expect(facts.owner).toBe(named((record.record as Record<string, any>).principals.person));
    expect(facts.audit).toMatchObject({ requests: audit.counts.requests, refused: audit.counts.refused, confirmed: audit.counts.confirmed_by_a_person });
    expect([facts.bed.before, facts.bed.after]).toEqual([bed[facts.bed.channel].before.value, bed[facts.bed.channel].after.value]);
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
    expect(bedRow.at.ask).toBe(bedRow.at.look);
  });

  it("cool the nozzle through the record's readings after the approved cancel, in whole degrees", () => {
    const cooling = approve.cooling as Array<Record<string, any>>;
    const whole = (view: Record<string, any>) => amount(Math.round(view.extruder_temp.value), view.extruder_temp.unit);
    const [nozzleRow, bedRow, stateRow] = facts.printer.readings;
    expect(cooling.length).toBeGreaterThan(1);
    expect(nozzleRow.at.approve).toBe(whole(approve.printer));
    expect(nozzleRow.cooling).toEqual(cooling.slice(0, -1).map((entry) => whole(entry.printer)));
    expect(nozzleRow.at.end).toBe(whole(cooling[cooling.length - 1].printer));
    expect(stateRow.at.end).toBe(cooling[cooling.length - 1].printer.state);
    for (const text of [...nozzleRow.cooling, nozzleRow.at.end]) expect(text).toMatch(/^\d+ °C$/);
    expect([nozzleRow.stale, bedRow.stale, stateRow.stale]).toEqual([false, true, false]);
    expect(printer.actions.cancel?.effects ?? []).not.toContain(facts.bed.channel);
  });

  it("take the limits from printer.hal.yaml, which match what the hub described", () => {
    const limits = record.record.devices!.find((item) => item.id === printer.id)!.limits;
    for (const channel of [facts.nozzle.channel, facts.bed.channel]) {
      expect(limits[channel].max.value).toBe(printer.write[channel].max);
      expect(limits[channel].max.unit).toBe(printer.write[channel].unit);
    }
    expect(facts.nozzle.max).toBe(amount(printer.write[facts.nozzle.channel].max, printer.write[facts.nozzle.channel].unit));
    expect(facts.bed.max).toBe(amount(printer.write[facts.bed.channel].max, printer.write[facts.bed.channel].unit));
    expect(printer.actions[facts.cancel.target]).toMatchObject({ confirm: expect.any(String) });
    expect(printer.actions[facts.pause.target]?.confirm).toBeUndefined();
  });

  it("follow the record when it changes", () => {
    const changed = fresh();
    const record = changed.record as Record<string, any>;
    byId(changed, IDS.nozzle).request.params.value = 290;
    byId(changed, IDS.nozzle).error!.data.name = "OUT_OF_RANGE";
    byId(changed, IDS.bed).request.params.value = 75;
    byId(changed, IDS.bed).bed_target.after.value = 75;
    for (const exchange of changed.record.exchanges as Array<Record<string, any>>) {
      for (const view of [exchange.printer, ...(exchange.cooling ?? []).map((entry: Record<string, any>) => entry.printer)]) if (view?.bed_target.value === 70) view.bed_target.value = 75;
    }
    byId(changed, IDS.cancel).before = "a cancelled print can't be resumed";
    byId(changed, IDS.approve).before = "the operator approves the cancel";
    byId(changed, IDS.approve).printer.state = "standby";
    byId(changed, IDS.approve).printer.extruder_temp.value = 214;
    byId(changed, IDS.approve).cooling.at(-1).printer.extruder_temp.value = 29.6;
    byId(changed, IDS.approve).by = "human:operator";
    record.principals.person = "human:operator";
    record.audit.counts.requests = 9;
    const other = storyFacts(changed, readDeviceFile());
    const lines = storyLines(other);
    const sequence = storySequence(other);
    expect(other.said.hot[0]).toEqual({ from: "agent", to: "hub", label: nb("extruder_target 290 °C"), answer: { text: "OUT_OF_RANGE", tone: "blocked" } });
    expect(lines.hot).toContain(nb("a nozzle temperature of 290 °C"));
    expect(other.said.warm[0].label).toBe(nb("bed_target 75 °C"));
    expect(lines.warm).toContain(nb("raises the bed to 75 °C"));
    expect(sequence.readings[1].values.map((value) => value.text)).toEqual(["60 °C", "75 °C"]);
    expect(sequence.heads).toEqual({ owner: "Operator", agent: "Agent", hub: "OpenHAL hub", printer: "Printer" });
    expect(other.said.approve[0].from).toBe("owner");
    expect(other.printer.readings[0].at.approve).toBe("214 °C");
    expect(other.printer.readings[0].at.end).toBe("30 °C");
    expect(lines.end).toContain("all 9 requests");
  });

  it("stop a refused bed target at the hub when the record says the hub refused it", () => {
    const changed = fresh();
    const warmed = byId(changed, IDS.bed);
    warmed.error = { code: -32010, message: "bed_target 70 degC exceeds the limit of 60 degC (printer.hal.yaml, confirmed by owner 2026-10-24)", data: { name: "LIMIT_EXCEEDED" } };
    delete warmed.result;
    const sequence = storySequence(storyFacts(changed, readDeviceFile()));
    const row = sequence.rows.find((item) => item.id === "warm")!;
    expect(row.legs.map((leg) => [leg.from, leg.to])).toEqual([["agent", "hub"]]);
    expect(row.reply).toMatchObject({ from: "hub", to: "agent", answer: { text: "LIMIT_EXCEEDED", tone: "blocked" } });
  });

  it("follow the device file when a person changes a limit", () => {
    const tighter = readDeviceFile();
    tighter.write[facts.nozzle.channel].max = 250;
    expect(storyLines(storyFacts(fresh(), tighter)).hot).toContain(nb("Your limit is 250 °C"));
  });

  it("are the owner's nine captions, with the record's values", () => {
    expect(Object.values(storyLines(facts)).map((line) => line.replace(/ /g, " "))).toEqual([
      "An agent watches a 3D print through the OpenHAL hub.",
      "You start a long print and ask an agent to watch it.",
      "The agent checks the webcam and sees a corner of the first layer lifting.",
      "The agent raises the bed to 70 °C. Your limit is 110 °C, so the hub lets the request through.",
      "The agent also tries a nozzle temperature of 300 °C to help the print stick. Your limit is 260 °C, so the hub refuses.",
      "Later, the webcam shows the print has come loose.",
      "The agent pauses the print. Pausing is safe, so no one has to approve it.",
      "Cancelling can't be undone, so the hub holds the request until you approve it.",
      "You approve, and the hub sends the cancel to the printer.",
      "The audit log records all 6 requests, including the refusal and your approval.",
    ]);
  });

  it("read in at most two plain sentences each, written to the owner's rules", () => {
    const opening: string[] = [];
    for (const [id, line] of Object.entries(storyLines(facts))) {
      const words = line.replace(/ /g, " ");
      const sentences = words.split(/(?<=[.?!])\s+/);
      opening.push(...sentences.map((sentence) => sentence.split(" ")[0]));
      expect(words, id).toMatch(/^[A-Z].*[.]$/);
      expect(sentences.length, id).toBeLessThanOrEqual(2);
      expect(words, id).not.toMatch(/[;:!–—]/);
      expect(words, id).not.toMatch(/\bAI\b/);
      for (const sentence of sentences) expect(sentence, id).not.toMatch(/^(It|Its|They|Them|That's)\b/);
      expect(words, id).not.toMatch(/\b(hub|kernel|OpenHAL)\b[^,.]*\b(says?|asks?|steps? in|wants?|decides?|thinks?|knows?|sees?)\b/);
      expect(words, id).not.toMatch(/\ba \d+ °C (nozzle|bed)\b/);
      expect(words.split(/\s+/).length, id).toBeLessThanOrEqual(32);
    }
    expect(opening.filter((word) => word === "Because" || word === "When").length).toBeLessThanOrEqual(1);
    expect(nb("warm to 70 °C")).toBe("warm to 70 °C");
    expect(humane("extruder_target 300 degC exceeds the limit of 260 degC")).toBe("extruder_target 300 °C exceeds the limit of 260 °C");
  });

  it("end on the audit log's count of requests, the refusal and the approval", () => {
    const end = storyLines(facts).end;
    expect(end).toContain(`all ${audit.counts.requests} requests`);
    expect(audit.counts.refused).toBe(1);
    expect(audit.counts.confirmed_by_a_person).toBe(1);
    expect(end).toContain("the refusal and your approval");
  });
});
