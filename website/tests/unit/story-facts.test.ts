import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { nb, readDeviceFile, storyFacts, storyLines } from "../../src/lib/story/facts";
import { ALWAYS, NEVER, TOTAL } from "../../src/lib/story/script";
import { CLIENT, DEVICE, DRIVER, FILLS, HUB, KERNEL, NOTE_AT, SNAP_AT, TITLE_OUT } from "../../src/lib/story/timeline";
import type { Scenario } from "../../src/lib/scenario";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = readFileSync(scenarioFile, "utf8");

describe("the story's timeline", () => {
  it("places every cue inside the story", () => {
    const points: number[] = [
      TITLE_OUT,
      ...Object.values(NOTE_AT),
      ...Object.values(SNAP_AT),
      ...[CLIENT, HUB, DRIVER].flatMap((station) => Object.values(station).flatMap((span) => [span.at, span.out])),
      ...[KERNEL.first, KERNEL.second, KERNEL.third].flatMap((group) => Object.values(group).flatMap((span) => [span.at, span.out])),
      ...[DEVICE.tank, DEVICE.pump].flatMap((group) => Object.values(group).flatMap((span) => [span.at, span.out])),
      DEVICE.soil.at,
      DEVICE.soil.at + DEVICE.soil.d,
      ...FILLS.flatMap((fill) => [fill.at, fill.at + fill.d, fill.out]),
    ].filter((point) => point !== ALWAYS && point !== NEVER);
    for (const point of points) {
      expect(point).toBeGreaterThanOrEqual(0);
      expect(point).toBeLessThanOrEqual(TOTAL);
    }
  });

  it("tells the scenario in order, blocking twice before it grants", () => {
    const times = Object.values(NOTE_AT);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(KERNEL.first.verdict.at).toBeLessThan(CLIENT.limit.at);
    expect(KERNEL.second.verdict.at).toBeLessThan(KERNEL.third.verdict.at);
    expect(DEVICE.tank.empty.at).toBeLessThan(KERNEL.second.interlocks.at);
    expect(DEVICE.tank.refilled.at).toBeLessThan(KERNEL.third.verdict.at);
    expect(KERNEL.third.verdict.at).toBeLessThanOrEqual(DRIVER.granted.at);
    expect(DEVICE.pump.on.at).toBeLessThan(DEVICE.soil.at);
    expect(CLIENT.done.at).toBeGreaterThan(DEVICE.soil.at + DEVICE.soil.d);
  });
});

describe("the story's words and numbers", () => {
  const facts = storyFacts();
  const record = scenarioFrom(recorded).record as Scenario["record"] & { limits: any; confirmed: any };
  const [tooLong, empty, watered] = record.exchanges;

  it("come from the recorded scenario", () => {
    expect(facts.asked).toBe(`${tooLong.request.params.args.duration.value} s`);
    expect(facts.ran).toBe(`${watered.request.params.args.duration.value} s`);
    expect(facts.max).toBe(`${record.limits.water_duration.max.value} s`);
    expect(facts.tooLong.name).toBe(tooLong.error!.data.name);
    expect(facts.empty.name).toBe(empty.error!.data.name);
    expect(facts.empty.reason).toBe(empty.error!.message);
    expect(facts.tooLong.reason).toBe(tooLong.error!.message.slice(0, tooLong.error!.message.indexOf(" (")));
    expect(facts.status).toBe(watered.result!.status);
    expect(facts.soil.before).toBe(watered.soil_moisture!.before.value);
    expect(facts.soil.after).toBe(watered.soil_moisture!.after.value);
    expect(facts.confirmed).toBe(`confirmed by ${record.confirmed.by} ${record.confirmed.at}`);
    expect(facts.method).toBe(tooLong.request.method);
  });

  it("follow the scenario when it changes", () => {
    const changed = recorded.replace(/value: 120/g, "value: 90").replace(/value: 46/g, "value: 52");
    const other = storyFacts(scenarioFrom(changed), readDeviceFile());
    expect(other.asked).toBe("90 s");
    expect(other.soil.after).toBe(52);
    expect(storyLines(other).ask).toContain("90 s");
    expect(storyLines(other).soil).toContain("52 %");
  });

  it("name the device, its driver and its interlock from the device file", () => {
    expect(facts.device).toBe("Arduino plant waterer");
    expect(facts.driver).toBe("openhal-firmware");
    expect(facts.tank).toEqual({ low: "empty", ok: "ok" });
  });

  it("read as short plain sentences that follow the copy rules", () => {
    for (const line of Object.values(storyLines(facts))) {
      expect(line).toMatch(/[.]$/);
      expect(line).not.toMatch(/[;:!–—]/);
      expect(line.split(/\s+/).length).toBeLessThanOrEqual(16);
    }
    expect(nb("water for 20 s")).toBe("water for 20 s");
  });
});
