import { Kernel, agent, deviceId, deviceRefs, human, label, loadDeviceFile, type Command, type DeviceFile, type Principal, type Request } from "../kernel";
import { formatG } from "../kernel/pyformat";
import { parseDeviceYaml } from "../kernel/yaml";
import { rpcError } from "../protocol";
import type { TraceEntry } from "../trace";
import { CliError, actionArgs, splitPairs, writeValue } from "./cli";
import { decisionWire, displayUnit, errorEntry, requestFor, responseFor } from "./rpc";
import { afterAction } from "./simulate";
import type { Exchange } from "./types";
import { deviceProblems, type Checked } from "./validate";

export interface Example {
  name: string;
  path: string;
  text: string;
}

export interface Suggestion {
  device: string;
  target: string;
  text: string;
  readings?: Record<string, unknown>;
}

export interface Quick {
  label: string;
  command: Command;
}

export interface Client {
  key: string;
  label: string;
  client: string;
  principal: Principal;
}

/** Who sent an exchange and what went over the wire, before the log gives it a key. */
export type Logged = Omit<Exchange, "key">;

export type Library = Map<string, { file: DeviceFile; path: string }>;

/** The clients a person can send as, from the strongest agent token to a person's own token. */
export const CLIENTS: Client[] = [
  { key: "agent-medium", label: "Agent, control_medium token", client: "claude", principal: agent("claude", "control_medium") },
  { key: "agent-low", label: "Agent, control_low token", client: "claude", principal: agent("claude", "control_low") },
  { key: "agent-read", label: "Agent, read token", client: "claude", principal: agent("claude", "read") },
  { key: "human", label: "Person, human token", client: "you", principal: human("you") },
];

/** How long the hub holds a request for a person, in seconds. */
export const TTL_S = 300;

/** How long the simulated devices have been running when the Playground opens, in seconds. */
const RUNNING_S = 30;

/** The most exchanges the log keeps, newest first. */
export const LOG_SIZE = 30;

const STOP_REASON = "stop pressed in the playground";

/** The clients' entry by key, falling back to the strongest agent. */
export function clientOf(key: string): Client {
  return CLIENTS.find((item) => item.key === key) ?? CLIENTS[0];
}

/**
 * Every example device file by its device id, so a file whose interlocks name another device can
 * load that device too. A file that says its limits are confirmed wins over one that doesn't.
 */
export function exampleFiles(examples: Example[]): Library {
  const found: Library = new Map();
  for (const item of examples) {
    try {
      const loaded = loadDeviceFile(parseDeviceYaml(item.text));
      const key = deviceId(loaded);
      if (!found.has(key) || item.text.includes("confirmed:")) found.set(key, { file: loaded, path: item.path });
    } catch {
      continue;
    }
  }
  return found;
}

/** The readings a simulated device starts with: the middle of each number range, and the story's own readings. */
export function simulatedValues(device: DeviceFile, suggestion: Suggestion | null): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(device.read)) {
    if (spec.type === "number" && spec.range) values[name] = Math.round(((spec.range[0] + spec.range[1]) / 2) * 100) / 100;
  }
  for (const [name, spec] of Object.entries(device.write)) {
    if (deviceId(device) === "desk-fan" && name === "fan_speed" && spec.type === "number") values[name] = 20;
  }
  if (suggestion?.readings && suggestion.device === deviceId(device)) Object.assign(values, suggestion.readings);
  return values;
}

export interface Built {
  kernel: Kernel;
  companions: Array<{ id: string; path: string }>;
}

/**
 * A fresh kernel with the device file and every device its interlocks name, connected and with
 * their readings noted as if the devices had been running for half a minute.
 */
export function buildKernel(next: DeviceFile, library: () => Library, suggestion: Suggestion | null): Built {
  let skew = 0;
  const kernel = new Kernel(() => performance.now() / 1000 + skew, { confirmTtlS: TTL_S });
  const mine = deviceId(next);
  const companions: Array<{ id: string; path: string }> = [];
  for (const ref of deviceRefs(next)) {
    const other = library().get(ref);
    if (other && ref !== mine) {
      kernel.register(other.file, simulatedValues(other.file, suggestion));
      companions.push({ id: ref, path: other.path });
    }
  }
  kernel.register(next, simulatedValues(next, suggestion));
  for (const device of kernel.devices.keys()) kernel.connect(device);
  skew = RUNNING_S;
  for (const [device, runtime] of kernel.devices) {
    for (const [channel, spec] of Object.entries(runtime.file.read)) {
      if (spec.type !== "image") kernel.noteReading(device, channel, runtime.values[channel], spec.unit);
    }
  }
  return { kernel, companions };
}

/**
 * The channel or action the request form starts on and the value it offers. A target that still
 * exists stays, the story's request comes first, and a number channel offers half again its limit.
 */
export function startingRequest(next: DeviceFile, suggestion: Suggestion | null, target: string, requestText: string): { target: string; requestText: string } {
  const mine = deviceId(next);
  const writes = Object.keys(next.write);
  const actions = Object.keys(next.actions);
  const suggested = suggestion && suggestion.device === mine && (writes.includes(suggestion.target) || actions.includes(suggestion.target)) ? suggestion : null;
  const chosen = writes.includes(target) || actions.includes(target) ? target : (suggested?.target ?? writes[0] ?? actions[0] ?? "");
  let text = requestText;
  const spec = next.write[chosen];
  if (!text && suggested && suggested.target === chosen) text = suggested.text;
  else if (!text && spec?.type === "number" && spec.max !== null) text = `${formatG(spec.max * 1.5)} ${displayUnit(spec.unit)}`;
  return { target: chosen, requestText: text };
}

export interface Session {
  checked: Checked;
  kernel: Kernel | null;
  companions: Array<{ id: string; path: string }>;
  targetDevice: string;
  target: string;
  requestText: string;
}

/**
 * Checks a device file and builds the simulated hub for it. When the file has a problem the hub is
 * gone and the request form keeps what it had.
 */
export function prepare(text: string, current: Pick<Session, "targetDevice" | "target" | "requestText">, library: () => Library, suggestion: Suggestion | null): Session {
  const checked = deviceProblems(text);
  const { targetDevice, target, requestText } = current;
  if (!checked.file) return { checked, kernel: null, companions: [], targetDevice, target, requestText };
  const { kernel, companions } = buildKernel(checked.file, library, suggestion);
  return { checked, kernel, companions, targetDevice: deviceId(checked.file), ...startingRequest(checked.file, suggestion, target, requestText) };
}

/** Notes every reading again and lets the kernel's clock run, once a second. */
export function tickAll(kernel: Kernel): void {
  for (const [device, runtime] of kernel.devices) {
    for (const [channel, spec] of Object.entries(runtime.file.read)) {
      if (spec.type === "image") continue;
      kernel.noteReading(device, channel, runtime.values[channel], spec.unit);
    }
  }
  kernel.tick();
}

function whoOf(principal: Principal): Logged["who"] {
  return principal.kind === "human" ? "person" : "agent";
}

function paramsOf(command: Command): Record<string, unknown> {
  return (requestFor(command) as { params: Record<string, unknown> }).params;
}

function fileOf(kernel: Kernel, device: string): DeviceFile | undefined {
  return kernel.devices.get(device)?.file;
}

/** Moves a simulated device to where a granted action leaves it, such as a paused printer. */
export function settle(kernel: Kernel, command: Command, status: string): void {
  if (command.kind !== "action" || status !== "done") return;
  const runtime = kernel.devices.get(command.device);
  if (!runtime) return;
  for (const [channel, value] of Object.entries(afterAction(runtime.file, command.action))) {
    runtime.values[channel] = value;
    kernel.noteReading(command.device, channel, value, runtime.file.read[channel].unit);
  }
}

/**
 * Sends the request form's write or action, or its dry run, and returns the exchange for the log.
 * A value the form can't read becomes the hub's INVALID_PARAMS error.
 */
export function sendRequest(kernel: Kernel, client: Client, device: string, target: string, words: string, dry = false): Logged | null {
  const runtime = kernel.devices.get(device);
  if (!runtime) return null;
  const who = whoOf(client.principal);
  const isWrite = target in runtime.file.write;
  const text = words.trim();
  let command: Command;
  try {
    command = isWrite
      ? { kind: "write", device, channel: target, ...writeValue(runtime.file, target, text) }
      : { kind: "action", device, action: target, args: actionArgs(runtime.file, target, text ? splitPairs(text) : []) };
  } catch (error) {
    if (!(error instanceof CliError)) throw error;
    return {
      who,
      client: client.client,
      entries: [
        { kind: "request", method: isWrite ? "hal/write" : "hal/action", params: { device, [isWrite ? "channel" : "action"]: target, value: text } },
        errorEntry(rpcError("INVALID_PARAMS", { problems: [error.message] })),
      ],
    };
  }
  if (dry) {
    const [decision] = kernel.dryRun([command], client.principal, true);
    return {
      who,
      client: client.client,
      entries: [
        { kind: "request", method: "hal/dryRun", params: { commands: [{ kind: command.kind, ...paramsOf(command) }] } },
        { kind: "result", result: { decisions: [decisionWire(decision, command, fileOf(kernel, command.device), label(client.principal))] } },
      ],
    };
  }
  const decision = kernel.execute(command, client.principal, null, true);
  settle(kernel, command, decision.status);
  return { who, client: client.client, entries: [requestFor(command), responseFor(decision, command, fileOf(kernel, command.device), TTL_S, label(client.principal))] };
}

/** Sends one of the story's requests as the agent with the control_medium token. */
export function sendQuick(kernel: Kernel, item: Quick): Logged | null {
  if (!kernel.devices.has(item.command.device)) return null;
  const sender = CLIENTS[0];
  const decision = kernel.execute(item.command, sender.principal, null, true);
  settle(kernel, item.command, decision.status);
  return { who: "agent", client: sender.client, entries: [requestFor(item.command), responseFor(decision, item.command, fileOf(kernel, item.command.device), TTL_S, label(sender.principal))] };
}

/** Stops every device as the person at the keyboard. */
export function stopAll(kernel: Kernel): Logged {
  const report = kernel.stopAll(human("you"), STOP_REASON);
  return {
    who: "person",
    client: "you",
    entries: [
      { kind: "request", method: "hal/stop", params: { reason: STOP_REASON } },
      { kind: "result", result: { devices: report.devices.map((item) => ({ device: item.device, status: item.status, detail: item.detail })) } },
    ],
  };
}

/** Lifts the stop with the phrase the person typed, or throws the kernel's reason. */
export function unlock(kernel: Kernel, phrase: string): Logged {
  kernel.unlock(human("you"), phrase);
  return {
    who: "person",
    client: "you",
    entries: [
      { kind: "request", method: "hal/unlock", params: { phrase: phrase.trim() } },
      { kind: "result", result: { ok: true } },
    ],
  };
}

/** Approves or rejects a request the hub holds for a person. */
export function decide(kernel: Kernel, requestId: string, approve: boolean): Logged {
  const request = kernel.requests.get(requestId)!;
  if (approve) {
    const decision = kernel.confirm(requestId, human("you"));
    settle(kernel, request.command, decision.status);
    return {
      who: "person",
      client: "you",
      entries: [
        { kind: "request", method: "hal/confirmations/approve", params: { requestId } },
        { kind: "result", result: decisionWire(decision, request.command, fileOf(kernel, request.command.device), label(request.principal)) },
      ],
    };
  }
  kernel.reject(requestId, human("you"));
  return {
    who: "person",
    client: "you",
    entries: [
      { kind: "request", method: "hal/confirmations/reject", params: { requestId } },
      {
        kind: "result",
        result: { requestId, status: "rejected", command: { kind: request.command.kind, ...paramsOf(request.command) }, requestedBy: label(request.principal), decidedBy: "human:you" },
      },
    ],
  };
}

/** Sets a simulated reading from the text a person typed, and returns false when the text isn't a value. */
export function setReading(kernel: Kernel, device: string, channel: string, draft: string): boolean {
  const runtime = kernel.devices.get(device);
  const spec = runtime?.file.read[channel];
  const text = draft.trim();
  if (!runtime || !spec || !text) return false;
  let value: unknown = text;
  if (spec.type === "number") {
    const number = Number(text);
    if (!Number.isFinite(number)) return false;
    value = number;
  } else if (spec.type === "bool") {
    value = ["true", "on", "yes", "1"].includes(text.toLowerCase());
  }
  runtime.values[channel] = value;
  kernel.noteReading(device, channel, value, spec.unit);
  return true;
}

/** The hint under the Value field for the chosen channel or action. */
export function hintFor(kernel: Kernel | null, device: string, target: string): string {
  const runtime = kernel?.devices.get(device);
  if (!runtime) return "";
  const spec = runtime.file.write[target];
  if (spec) {
    if (spec.type === "number") return `A number with a unit, for example ${formatG(spec.max ?? 0)} ${displayUnit(spec.unit)}`;
    if (spec.type === "bool") return "true or false";
    if (spec.type === "enum") return `One of ${spec.values.join(", ")}`;
    return `Text, at most ${spec.max_length} characters`;
  }
  const action = runtime.file.actions[target];
  if (action) {
    const names = Object.keys(action.args);
    return names.length ? `Arguments as key=value, for example ${names.map((name) => `${name}=…`).join(" ")}` : "No arguments";
  }
  return "";
}

/** The channels and actions of a device, writes first, as the request form lists them. */
export function targetsOf(kernel: Kernel | null, device: string): Array<{ name: string; kind: "write" | "action" }> {
  const runtime = kernel?.devices.get(device);
  if (!runtime) return [];
  return [
    ...Object.keys(runtime.file.write).map((name) => ({ name, kind: "write" as const })),
    ...Object.keys(runtime.file.actions).map((name) => ({ name, kind: "action" as const })),
  ];
}

/** A unit the way a person reads it, °C rather than degC. */
export function people(unit: string | null): string {
  const shown = displayUnit(unit);
  return shown === "degC" ? "°C" : shown === "degF" ? "°F" : (shown ?? "");
}

/** The story's channels to show beside its requests, on the device the requests go to. */
export function watchedChannels(kernel: Kernel | null, ready: Quick[], watch: string[]): Array<{ device: string; name: string; unit: string }> {
  const device = ready[0]?.command.device;
  const runtime = device ? kernel?.devices.get(device) : undefined;
  if (!device || !runtime) return [];
  return watch
    .filter((name) => name in runtime.file.write || name in runtime.file.read)
    .map((name) => ({ device, name, unit: people(runtime.file.write[name]?.unit ?? runtime.file.read[name]?.unit ?? null) }));
}

/** A value as the readout shows it, with numbers in the kernel's own format. */
export function show(value: unknown): string {
  if (value === null || value === undefined) return "unknown";
  if (typeof value === "number") return formatG(value);
  return String(value);
}

const NO_BREAK = String.fromCharCode(160);

/** A value and its unit joined by a no-break space, so the two never wrap apart. */
export function withUnit(value: string, unit: string | null): string {
  return unit ? `${value}${NO_BREAK}${unit}` : value;
}

/** How often a channel needs a person's approval, in the device table's words. */
export function tierWord(tier: string, high: boolean): string {
  if (high || tier === "confirm-each-time") return "each time";
  if (tier === "confirm") return "once";
  return "none";
}

/** What a held request asks for, such as `fan_speed 80` or `cancel`. */
export function heldWhat(request: Request): string {
  return request.command.kind === "write" ? `${request.command.channel} ${String(request.command.value)}` : request.command.action;
}
