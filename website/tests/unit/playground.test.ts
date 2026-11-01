import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CLIENTS,
  clientOf,
  decide,
  exampleFiles,
  hintFor,
  people,
  prepare,
  sendQuick,
  sendRequest,
  setReading,
  show,
  startingRequest,
  stopAll,
  targetsOf,
  tierWord,
  unlock,
  watchedChannels,
  type Example,
  type Quick,
  type Suggestion,
} from "../../src/lib/playground/session";
import type { TraceEntry } from "../../src/lib/trace";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const example = (path: string): Example => ({ name: path.split("/").pop()!.replace(/\.hal\.yaml$/, ""), path, text: readFileSync(`${root}${path}`, "utf8") });
const EXAMPLES = [
  example("examples/print-babysitter/printer.hal.yaml"),
  example("examples/print-babysitter/printer-cam.hal.yaml"),
  example("spec/examples/desk-fan.hal.yaml"),
  example("spec/examples/desk-fan-confirmed.hal.yaml"),
  example("spec/examples/grbl-laser.hal.yaml"),
];
const library = () => exampleFiles(EXAMPLES);
const text = (name: string) => EXAMPLES.find((item) => item.name === name)!.text;
const empty = { targetDevice: "", target: "", requestText: "" };
const SUGGESTION: Suggestion = { device: "printer", target: "extruder_target", text: "300 degC", readings: { bed_target: 60, state: "printing" } };
const QUICK: Quick[] = [
  { label: "Set the nozzle to 300 °C", command: { kind: "write", device: "printer", channel: "extruder_target", value: 300, unit: "degC" } },
  { label: "Pause the print", command: { kind: "action", device: "printer", action: "pause", args: {} } },
  { label: "Cancel the print", command: { kind: "action", device: "printer", action: "cancel", args: {} } },
];

const head = (entry: TraceEntry) => (entry.kind === "error" ? `error ${entry.code} ${entry.name}` : entry.kind === "result" ? "result" : entry.kind === "note" ? "#" : entry.method);
const resultOf = (entry: TraceEntry) => (entry.kind === "result" ? (entry.result as Record<string, unknown>) : {});

describe("the Playground's simulated hub", () => {
  it("prefers the confirmed copy of a device file when two share an id", () => {
    expect(library().get("desk-fan")?.path).toBe("spec/examples/desk-fan-confirmed.hal.yaml");
  });

  it("opens on the story's request with the story's readings", () => {
    const session = prepare(text("printer"), empty, library, SUGGESTION);
    expect(session.checked.problems).toEqual([]);
    expect(session.targetDevice).toBe("printer");
    expect(session.target).toBe("extruder_target");
    expect(session.requestText).toBe("300 degC");
    expect(session.kernel!.latestValue("printer", "state")).toBe("printing");
    expect(watchedChannels(session.kernel, QUICK, ["bed_target", "state"])).toEqual([
      { device: "printer", name: "bed_target", unit: "°C" },
      { device: "printer", name: "state", unit: "" },
    ]);
  });

  it("offers half again a number channel's limit when the story has no request for the file", () => {
    const session = prepare(text("desk-fan-confirmed"), empty, library, SUGGESTION);
    expect(session.target).toBe("fan_speed");
    expect(session.requestText).toBe("150 %");
    expect(startingRequest(session.checked.file!, null, "fan_speed", "40 %")).toEqual({ target: "fan_speed", requestText: "40 %" });
  });

  it("keeps the form and drops the hub when the device file has a problem", () => {
    const session = prepare("device: Fan\nconnect: { mock: fan }\nwrite:\n  speed: { unit: percent, min: 0 }\n", { targetDevice: "printer", target: "bed_target", requestText: "70 degC" }, library, null);
    expect(session.kernel).toBeNull();
    expect(session.checked.problems.map((problem) => problem.message)).toContain("Number values need both min and max.");
    expect(session.target).toBe("bed_target");
  });

  it("answers an over-limit write with the registry error, word for word", () => {
    const { kernel } = prepare(text("desk-fan-confirmed"), empty, library, null);
    const logged = sendRequest(kernel!, CLIENTS[0], "desk-fan", "fan_speed", "150 %")!;
    expect(logged.who).toBe("agent");
    expect(logged.entries.map(head)).toEqual(["hal/write", "error -32010 LIMIT_EXCEEDED"]);
    expect(logged.entries[1]).toMatchObject({ reason: "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by owner 2026-10-24)" });
  });

  it("turns a value the form can't read into INVALID_PARAMS", () => {
    const { kernel } = prepare(text("desk-fan-confirmed"), empty, library, null);
    const logged = sendRequest(kernel!, CLIENTS[0], "desk-fan", "fan_speed", "  ")!;
    expect(logged.entries[0]).toEqual({ kind: "request", method: "hal/write", params: { device: "desk-fan", channel: "fan_speed", value: "" } });
    expect(logged.entries[1].kind).toBe("error");
    expect(JSON.stringify(logged.entries[1])).toContain("Give a value, with a unit for numbers, for example 60 % or 25 degC.");
  });

  it("reports a dry run's decision without changing the device", () => {
    const { kernel } = prepare(text("desk-fan-confirmed"), empty, library, null);
    const logged = sendRequest(kernel!, CLIENTS[0], "desk-fan", "fan_speed", "150 %", true)!;
    expect(logged.entries.map(head)).toEqual(["hal/dryRun", "result"]);
    expect(JSON.stringify(logged.entries[1])).toContain("LIMIT_EXCEEDED");
    expect(kernel!.latestValue("desk-fan", "fan_speed")).toBe(20);
  });

  it("blocks a read token from a medium hazard device", () => {
    const { kernel } = prepare(text("printer"), empty, library, SUGGESTION);
    const logged = sendRequest(kernel!, clientOf("agent-read"), "printer", "bed_target", "70 degC")!;
    expect(logged.entries.map(head)).toEqual(["hal/write", "error -32003 SCOPE_DENIED"]);
  });

  it("sends the story's requests as the agent, holds the cancel and runs it once a person approves", () => {
    const { kernel } = prepare(text("printer"), empty, library, SUGGESTION);
    expect(sendQuick(kernel!, QUICK[0])!.entries.map(head)).toEqual(["hal/write", "error -32010 LIMIT_EXCEEDED"]);
    expect(resultOf(sendQuick(kernel!, QUICK[1])!.entries[1]).status).toBe("done");
    expect(kernel!.latestValue("printer", "state")).toBe("paused");
    expect(resultOf(sendQuick(kernel!, QUICK[2])!.entries[1]).status).toBe("pending");
    const [held] = kernel!.pending();
    const approved = decide(kernel!, held.requestId, true);
    expect(approved.who).toBe("person");
    expect(approved.entries.map(head)).toEqual(["hal/confirmations/approve", "result"]);
    expect(resultOf(approved.entries[1]).status).toBe("done");
    expect(kernel!.latestValue("printer", "state")).toBe("cancelled");
    expect(kernel!.pending()).toEqual([]);
  });

  it("records a person's rejection with who asked and who decided", () => {
    const { kernel } = prepare(text("printer"), empty, library, SUGGESTION);
    sendQuick(kernel!, QUICK[2]);
    const [held] = kernel!.pending();
    const rejected = decide(kernel!, held.requestId, false);
    expect(rejected.entries.map(head)).toEqual(["hal/confirmations/reject", "result"]);
    expect(resultOf(rejected.entries[1])).toMatchObject({ status: "rejected", requestedBy: "agent:claude", decidedBy: "human:you" });
  });

  it("blocks every request after a stop until a person types unlock", () => {
    const { kernel } = prepare(text("printer"), empty, library, SUGGESTION);
    const stop = stopAll(kernel!);
    expect(stop.entries[0]).toEqual({ kind: "request", method: "hal/stop", params: { reason: "stop pressed in the playground" } });
    expect(kernel!.stopped).toBe(true);
    expect(JSON.stringify(sendQuick(kernel!, QUICK[1])!.entries[1])).toContain("STOPPED");
    expect(() => unlock(kernel!, "open")).toThrow();
    expect(unlock(kernel!, " unlock ").entries[0]).toEqual({ kind: "request", method: "hal/unlock", params: { phrase: "unlock" } });
    expect(kernel!.stopped).toBe(false);
  });

  it("sets a simulated reading only from a value of the channel's type", () => {
    const { kernel } = prepare(text("grbl-laser"), empty, library, null);
    expect(setReading(kernel!, "laser", "door_closed", "yes")).toBe(true);
    expect(kernel!.latestValue("laser", "door_closed")).toBe(true);
    expect(setReading(kernel!, "laser", "door_closed", "")).toBe(false);
  });

  it("explains each kind of value under the Value field", () => {
    const { kernel } = prepare(text("grbl-laser"), empty, library, null);
    expect(hintFor(kernel, "laser", "laser_power")).toBe("A number with a unit, for example 30 %");
    expect(hintFor(kernel, "laser", "run_job")).toBe("Arguments as key=value, for example file=…");
    expect(hintFor(kernel, "laser", "home")).toBe("No arguments");
    expect(targetsOf(kernel, "laser").map((item) => `${item.name} ${item.kind}`)).toEqual(["laser_power write", "home action", "run_job action", "feed_hold action"]);
  });

  it("shows values and units the way a person reads them", () => {
    expect(show(null)).toBe("unknown");
    expect(show(0.5)).toBe("0.5");
    expect(people("degC")).toBe("°C");
    expect(people("percent")).toBe("%");
    expect(tierWord("none", true)).toBe("each time");
    expect(tierWord("confirm", false)).toBe("once");
    expect(tierWord("none", false)).toBe("none");
  });
});
