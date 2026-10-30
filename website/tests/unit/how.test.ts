import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { IDS, readDeviceFile, storyFacts } from "../../src/lib/story/facts";
import { CAPTIONS, COLUMNS, TIP, across, howSteps, howStepsFor, type Reply, type Request, type Span } from "../../src/lib/story/how";
import type { Scenario } from "../../src/lib/scenario";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = readFileSync(scenarioFile, "utf8");
const fresh = () => scenarioFrom(recorded) as Scenario;
const facts = storyFacts();
const steps = howSteps(facts);
const ends = ([at, length]: Span) => at + length;
const requests = (index: number) => steps[index].rows.filter((row): row is Request => row.kind === "request");
const replies = (index: number) => steps[index].rows.filter((row): row is Reply => row.kind === "reply");
const byId = (id: string) => fresh().record.exchanges.find((exchange) => exchange.id === id)!;

describe("How it works", () => {
  it("tells three steps in the owner's captions, with the hub and the printer acting like machines", () => {
    expect(steps.map((step) => step.caption)).toEqual([
      "The agent sends a request to set the bed to 70 °C. Your limit is 110 °C, so the hub passes the request to the printer.",
      "The agent sends a request to set the nozzle to 300 °C. Your limit is 260 °C, so the hub blocks the request.",
      "The agent sends a request to cancel the print. A cancel can't be undone, so the hub holds the request for your approval.",
    ]);
    for (const caption of CAPTIONS) expect(caption).not.toMatch(/[;:!–—]/);
  });

  it("says the numbers the record and the device file hold", () => {
    expect(CAPTIONS[0]).toContain(`set the bed to ${facts.bed.value}.`);
    expect(CAPTIONS[0]).toContain(`Your limit is ${facts.bed.max},`);
    expect(CAPTIONS[1]).toContain(`set the nozzle to ${facts.nozzle.value}.`);
    expect(CAPTIONS[1]).toContain(`Your limit is ${facts.nozzle.max},`);
    expect(readDeviceFile().actions.cancel?.confirm).toBe("confirm-each-time");
    expect(byId(IDS.cancel).result?.status).toBe("pending");
  });

  it("draws one diagram of Agent, OpenHAL hub and Printer", () => {
    expect(COLUMNS).toEqual(["agent", "hub", "printer"]);
    expect(steps.map((step) => step.readings.map((reading) => reading.name))).toEqual([
      ["Nozzle", "Bed", "State"],
      ["Nozzle", "Bed", "State"],
      ["Nozzle", "Bed", "State"],
    ]);
    expect(steps.map((step) => step.rule.text)).toEqual([`Bed ≤ ${facts.bed.max}`, `Nozzle ≤ ${facts.nozzle.max}`, "Cancel needs approval"]);
  });

  it("passes the bed write to the printer, and done returns while the bed changes from 60 °C to 70 °C", () => {
    const [request] = requests(0);
    expect(request.label).toBe(facts.said.warm[0].label);
    expect(request.legs.map((leg) => [leg.from, leg.to, leg.held])).toEqual([
      ["agent", "hub", false],
      ["hub", "printer", false],
    ]);
    expect(replies(0)).toMatchObject([{ from: "printer", answer: "done", tone: "ok" }]);
    const bed = steps[0].readings.find((reading) => reading.name === "Bed")!;
    expect([bed.value, bed.becomes?.value]).toEqual(["60 °C", "70 °C"]);
    expect(bed.becomes!.at[0]).toBeGreaterThanOrEqual(ends(request.legs[1].draws));
    expect(replies(0)[0].draws[0]).toBeGreaterThanOrEqual(ends(bed.becomes!.at));
  });

  it("stops the nozzle request at the hub, and LIMIT_EXCEEDED returns while the printer stays as it was", () => {
    const [request] = requests(1);
    expect(request.label).toBe(facts.said.hot[0].label);
    expect(request.legs.map((leg) => [leg.from, leg.to])).toEqual([["agent", "hub"]]);
    expect(replies(1)).toMatchObject([{ from: "hub", answer: byId(IDS.nozzle).error!.data.name, tone: "blocked" }]);
    expect(steps[1].readings.every((reading) => !reading.becomes)).toBe(true);
    expect(steps[1].readings.map((reading) => reading.value)).toEqual(steps[0].readings.map((reading) => reading.becomes?.value ?? reading.value));
  });

  it("holds the cancel at the hub as pending in amber until Approve sends it on, and done returns as the state becomes cancelled", () => {
    const [cancel, approve] = requests(2);
    expect(cancel.label).toBe("cancel");
    expect(cancel.legs).toMatchObject([{ from: "agent", to: "hub", held: true }]);
    expect(approve).toMatchObject({ label: "Approve", approve: true, legs: [{ from: "hub", to: "printer", held: false }] });
    expect(replies(2)).toMatchObject([
      { from: "hub", answer: "pending", tone: "confirm" },
      { from: "printer", answer: "done", tone: "ok" },
    ]);
    const state = steps[2].readings.find((reading) => reading.name === "State")!;
    expect([state.value, state.becomes?.value]).toEqual(["printing", (byId(IDS.approve) as Record<string, any>).printer.state]);
    expect(steps[2].rows.map((row) => row.kind)).toEqual(["request", "reply", "request", "reply"]);
  });

  it("times every piece inside its step, each after the one it follows, and holds the step at its end", () => {
    for (const [index, step] of steps.entries()) {
      const spans: Span[] = [step.rule.shows];
      let last = 0;
      for (const row of step.rows) {
        if (row.kind === "request") {
          spans.push(row.shows);
          expect(row.legs[0].draws[0], `step ${index + 1}`).toBeGreaterThanOrEqual(ends(row.shows) - 0.001);
          for (const [place, leg] of row.legs.entries()) {
            spans.push(leg.draws);
            if (place > 0) expect(leg.draws[0]).toBeGreaterThan(ends(row.legs[place - 1].draws));
            expect(leg.draws[0], `step ${index + 1}`).toBeGreaterThanOrEqual(last);
            last = ends(leg.draws);
          }
        } else {
          spans.push(row.draws);
          expect(row.draws[0], `step ${index + 1}`).toBeGreaterThan(last);
          last = ends(row.draws);
        }
      }
      for (const span of spans) {
        expect(span[0]).toBeGreaterThanOrEqual(0);
        expect(ends(span)).toBeLessThanOrEqual(0.95);
      }
      expect(step.rule.shows[0]).toBeGreaterThanOrEqual(ends(requests(index)[0].legs[0].draws) - TIP);
    }
  });

  it("places each step's pieces in its own third of the section's scroll", () => {
    expect(across(0, 3, [0, 1])).toEqual([0, 1 / 3]);
    const [at, length] = across(2, 3, [0.5, 0.3]);
    expect(at).toBeCloseTo(2.5 / 3, 9);
    expect(length).toBeCloseTo(0.1, 9);
  });

  it("follows the record when the record changes", () => {
    const changed = fresh();
    const bed = changed.record.exchanges.find((exchange) => exchange.id === IDS.bed)! as Record<string, any>;
    bed.request.params.value = 75;
    const other = howStepsFor(changed, readDeviceFile());
    expect((other[0].rows[0] as Request).label).toBe("bed_target 75 °C");
    const nozzle = changed.record.exchanges.find((exchange) => exchange.id === IDS.nozzle)!;
    nozzle.error!.data.name = "OUT_OF_RANGE";
    expect(howStepsFor(changed, readDeviceFile())[1].rows[1]).toMatchObject({ answer: "OUT_OF_RANGE", tone: "blocked" });
  });
});
