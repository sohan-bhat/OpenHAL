import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Kernel, type Command, type Decision, type Principal, deviceId, human, label, limitsSha256, loadDeviceFile } from "../../src/lib/kernel";
import { decisionWire } from "../../src/lib/playground/rpc";
import { parseDeviceYaml } from "../../src/lib/kernel/yaml";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const parity = fileURLToPath(new URL("../kernel-parity/", import.meta.url));
const spec = JSON.parse(readFileSync(`${parity}cases.json`, "utf8"));
const expected = JSON.parse(readFileSync(`${parity}expected.json`, "utf8"));

type Step = Record<string, any>;

function deviceText(name: string): string {
  if (name in spec.files) return readFileSync(`${root}${spec.files[name]}`, "utf8");
  return spec.inline[name];
}

function commandOf(data: Record<string, any>): Command {
  if ("action" in data) return { kind: "action", device: data.device, action: data.action, args: data.args ?? {} };
  return { kind: "write", device: data.device, channel: data.channel, value: data.value };
}

function decided(decision: Decision) {
  return { status: decision.status, code: decision.code, message: decision.message };
}

function onTheWire(kernel: Kernel, decision: Decision, command: Command, principal: Principal) {
  const file = kernel.devices.get(decision.device)?.file;
  let wire = decisionWire(decision, command, file, label(principal));
  if (decision.request_id) wire = JSON.parse(JSON.stringify(wire).replaceAll(decision.request_id, "REQUEST_ID"));
  return { ...decided(decision), wire };
}

class Clock {
  now = 1000;
  read = () => this.now;
}

function runCase(item: Record<string, any>) {
  const clock = new Clock();
  const kernel = new Kernel(clock.read);
  const principal: Principal = spec.principals[item.principal ?? "agent"];
  for (const entry of item.devices) {
    const [name, connect] = typeof entry === "string" ? [entry, true] : [entry.name, entry.connect ?? true];
    const file = loadDeviceFile(parseDeviceYaml(deviceText(name)));
    kernel.register(file, item.initial?.[deviceId(file)] ?? {});
    if (connect) kernel.connect(deviceId(file));
  }
  const steps: unknown[] = [];
  for (const step of (item.steps ?? []) as Step[]) {
    if ("advance" in step) clock.now += step.advance;
    else if ("execute" in step) {
      const command = commandOf(step.execute);
      for (let i = 0; i < (step.repeat ?? 1); i++) steps.push(onTheWire(kernel, kernel.execute(command, principal), command, principal));
    } else if ("reading" in step) {
      const r = step.reading;
      kernel.noteReading(r.device, r.channel, r.value, r.unit ?? null);
    } else if ("mark_unknown" in step) {
      const [device, channel] = step.mark_unknown.split(".");
      const runtime = kernel.devices.get(device)!;
      runtime.unknownSince.set(channel, clock.now);
      runtime.reads.delete(channel);
      runtime.accepted.delete(channel);
    } else if ("stop" in step) {
      const report = kernel.stopAll(spec.principals[step.stop], "parity stop");
      steps.push({ status: "stop", devices: report.devices.map((d) => [d.device, d.status]) });
    } else if ("unlock" in step) kernel.unlock(human(), step.unlock);
    else if ("tighten" in step) {
      const { device, channel, ...limits } = step.tighten;
      try {
        steps.push({ status: "tightened", limits: kernel.tighten(principal, device, channel, limits) });
      } catch (error: any) {
        if (error.code) steps.push({ status: "blocked", code: error.code, message: error.message });
        else steps.push({ status: "error", code: null, message: error.message });
      }
    } else if ("approve" in step) {
      const pending = kernel.pending();
      steps.push(decided(kernel.confirm(pending[pending.length - 1].requestId, human())));
    } else if ("unregister" in step) kernel.unregister(step.unregister);
    else if ("disconnect" in step) kernel.connectionLost(step.disconnect);
    else if ("tick" in step) steps.push({ status: "tick", fired: kernel.tick() });
    else throw new Error(`Unknown step ${JSON.stringify(step)}`);
  }
  const command = commandOf(item.command);
  const result = item.run === "execute" ? kernel.execute(command, principal) : kernel.evaluate(command, principal);
  return { id: item.id, steps, result: onTheWire(kernel, result, command, principal) };
}

describe("kernel parity with the Python kernel", () => {
  const wanted = new Map<string, unknown>(expected.cases.map((c: { id: string }) => [c.id, c]));
  for (const item of spec.cases) {
    it(item.id, () => {
      expect(runCase(item)).toEqual(wanted.get(item.id));
    });
  }
});

describe("limits hash parity", () => {
  for (const [path, hash] of Object.entries(expected.hashes as Record<string, string>)) {
    it(path, () => {
      const text = path.startsWith("inline:") ? spec.inline[path.slice(7)] : readFileSync(`${root}${path}`, "utf8");
      expect(limitsSha256(loadDeviceFile(parseDeviceYaml(text)))).toBe(hash);
    });
  }
});
