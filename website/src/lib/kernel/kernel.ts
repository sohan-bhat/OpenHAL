import { Block, checkRate, effectiveLimits, normalize, type Tightened } from "./checks";
import * as expr from "./expressions";
import {
  type ActionSpec,
  type DeviceFile,
  type MaxDuration,
  type WriteChannel,
  channelNames,
  conditions,
  channelUnit,
  deviceId,
  effectiveHazard,
  unconfirmed,
  writable,
} from "./model";
import { formatG, pyStrRepr } from "./pyformat";
import { UnitError, convert, formatQuantity, parseQuantity, parseRate } from "./units";

export type Kind = "human" | "agent" | "routine" | "system";
export type Scope = "read" | "control_low" | "control_medium";

export interface Principal {
  kind: Kind;
  name: string;
  scope: Scope;
}

const SCOPE_RANK: Record<Scope, number> = { read: 0, control_low: 1, control_medium: 2 };
const HAZARD_SCOPE: Record<string, Scope> = { low: "control_low", medium: "control_medium", high: "control_medium" };

export const SYSTEM: Principal = { kind: "system", name: "kernel", scope: "control_medium" };
export const human = (name = "owner"): Principal => ({ kind: "human", name, scope: "control_medium" });
export const agent = (name: string, scope: Scope = "read"): Principal => ({ kind: "agent", name, scope });
export const routine = (name: string, scope: Scope = "control_low"): Principal => ({ kind: "routine", name, scope });

export function label(principal: Principal): string {
  return `${principal.kind}:${principal.name}`;
}

function covers(principal: Principal, hazard: string): boolean {
  if (principal.kind === "human" || principal.kind === "system") return true;
  return SCOPE_RANK[principal.scope] >= SCOPE_RANK[HAZARD_SCOPE[hazard]];
}

export interface WriteCommand {
  kind: "write";
  device: string;
  channel: string;
  value: unknown;
  unit?: string | null;
}

export interface ActionCommand {
  kind: "action";
  device: string;
  action: string;
  args: Record<string, unknown>;
}

export type Command = WriteCommand | ActionCommand;

export function target(command: Command): string {
  return command.kind === "write" ? `write:${command.channel}` : `action:${command.action}`;
}

export type Status = "allowed" | "blocked" | "needs_confirmation" | "done" | "pending" | "failed";

export interface Decision {
  status: Status;
  code: string | null;
  message: string;
  device: string;
  target: string;
  value: unknown;
  unit: string | null;
  limit: Record<string, unknown> | null;
  request_id: string | null;
}

interface Sample {
  value: unknown;
  at: number;
  commanded: boolean;
}

interface RuleState {
  rule: MaxDuration;
  tree: expr.Node;
  activeSince: number | null;
  falseSince: number | null;
  exhausted: boolean;
  applied: boolean;
  failures: number;
  retryAt: number;
}

export interface Runtime {
  file: DeviceFile;
  values: Record<string, unknown>;
  connected: boolean;
  connectedAt: number;
  faulted: string | null;
  referenceProblem: string | null;
  applyingSafeState: boolean;
  reads: Map<string, Sample>;
  accepted: Map<string, Sample>;
  unknownSince: Map<string, number>;
  rules: RuleState[];
  runs: Map<string, number[]>;
}

export interface Request {
  requestId: string;
  command: Command;
  principal: Principal;
  createdAt: number;
  expiresAt: number;
  dryRun: Decision;
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled" | "blocked" | "done" | "failed";
  decidedBy: string | null;
  result: Decision | null;
}

export interface DeviceStopResult {
  device: string;
  status: "safe" | "partial" | "failed" | "pending" | "no_safe_state";
  detail: string;
}

export interface Shadow {
  values: Map<string, unknown>;
  stamps: Map<string, number>;
  now: number;
  runs?: Map<string, number[]>;
}

const UNKNOWN = Symbol("unknown");
const APPROVAL_WINDOW_S = 600;
const UNLOCK_PHRASE = "unlock";
const WATCHDOG_MAX_FAILURES = 3;

function key(...parts: string[]): string {
  return parts.join("\u0000");
}

function newestOf(samples: Sample[]): Sample {
  let best = samples[0];
  for (const sample of samples.slice(1)) if (sample.at > best.at) best = sample;
  return best;
}

function knownSamples(runtime: Runtime, channel: string): Sample[] {
  const cutoff = runtime.unknownSince.get(channel);
  let samples = [runtime.reads.get(channel), runtime.accepted.get(channel)].filter((s): s is Sample => s !== undefined);
  if (cutoff !== undefined) samples = samples.filter((sample) => sample.at >= cutoff);
  return samples;
}

function staleAfter(runtime: Runtime): number {
  return Math.max(10, 3 * runtime.file.watchdog.heartbeat);
}

function latest(runtime: Runtime, channel: string, now: number): Sample | null {
  const candidates = knownSamples(runtime, channel);
  if (!candidates.length) return null;
  const newest = newestOf(candidates);
  if (!(channel in runtime.file.write) && !newest.commanded && now - newest.at > staleAfter(runtime)) return null;
  return newest;
}

function markUnknown(runtime: Runtime, channel: string, now: number): void {
  runtime.unknownSince.set(channel, now);
  runtime.reads.delete(channel);
  runtime.accepted.delete(channel);
}

function availability(runtime: Runtime): string | null {
  if (!runtime.connected) return "not connected";
  if (runtime.faulted) return `in a fault state (${runtime.faulted})`;
  if (runtime.applyingSafeState) return "applying its safe state";
  return null;
}

function asValue(target: Runtime, channel: string, raw: unknown): expr.Value | null {
  if (raw === null || raw === undefined || raw === UNKNOWN) return null;
  if (typeof raw === "boolean" || typeof raw === "string") return { value: raw, unit: null };
  if (typeof raw === "number") return { value: raw, unit: channelUnit(target.file, channel) };
  return null;
}

export function deviceRefs(file: DeviceFile): string[] {
  return [...new Set(fileRefs(file).map((ref) => ref.device).filter((device): device is string => !!device))].sort();
}

function fileRefs(file: DeviceFile): expr.Ref[] {
  const names = channelNames(file);
  const texts = [
    ...file.interlocks.map((item) => item.if_),
    ...file.interlocks.map((item) => item.require),
    ...Object.values(file.actions).flatMap((action) => conditions(action).map(([condition]) => condition)),
    ...file.watchdog.max_duration.map((rule) => rule.when),
  ];
  const found = new Map<string, expr.Ref>();
  for (const text of texts) {
    for (const ref of expr.references(expr.parseCached(text, names))) found.set(`${ref.device}.${ref.name}`, ref);
  }
  return [...found.values()];
}

function seconds(value: number): string {
  if (value >= 3600 && value % 3600 === 0) return `${formatG(value / 3600)} h`;
  if (value >= 60 && value % 60 === 0) return `${formatG(value / 60)} min`;
  return `${formatG(value)} s`;
}

function display(value: unknown, unit: string | null): string {
  if (typeof value === "number" && unit) return formatQuantity(value, unit);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function quantityText(raw: unknown, unit: string | null): unknown {
  if (unit !== null && (typeof raw === "number" || typeof raw === "bigint")) return `${raw} ${unit}`;
  return raw;
}

function safeValueFor(file: DeviceFile, channel: string, raw: unknown): number | boolean | string {
  const spec = file.write[channel];
  return normalize(channel, spec, quantityText(raw, spec.unit));
}

function safeValue(file: DeviceFile, channel: string): number | null {
  for (const step of file.safe_state) {
    if (channel in step.values) {
      const value = safeValueFor(file, channel, step.values[channel]);
      if (typeof value === "number") return value;
    }
  }
  return null;
}

export function defaultValues(file: DeviceFile, initial: Record<string, unknown> = {}): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(file.write)) {
    if (name in initial) values[name] = initial[name];
    else if (spec.type === "number") values[name] = spec.min;
    else if (spec.type === "bool") values[name] = false;
    else if (spec.type === "enum") values[name] = spec.values[0];
    else values[name] = "";
  }
  for (const [name, spec] of Object.entries(file.read)) {
    if (name in initial) values[name] = initial[name];
    else if (spec.type === "number") values[name] = 0;
    else if (spec.type === "bool") values[name] = false;
    else if (spec.type === "enum") values[name] = spec.values[0];
    else if (spec.type === "image") values[name] = null;
    else values[name] = "";
  }
  return values;
}

export class KernelError extends Error {
  constructor(
    public kind: "permission" | "lookup" | "value",
    message: string,
  ) {
    super(message);
  }
}

export class Kernel {
  devices = new Map<string, Runtime>();
  stopped = false;
  stopReason: string | null = null;
  requests = new Map<string, Request>();
  confirmTtlS: number;
  private sessionLimits = new Map<string, Tightened>();
  private approvalWindows = new Map<string, number>();
  private orphans = new Map<string, DeviceFile>();
  private requestCounter = 0;

  constructor(
    public clock: () => number = () => performance.now() / 1000,
    options: { confirmTtlS?: number } = {},
  ) {
    this.confirmTtlS = options.confirmTtlS ?? 300;
  }


  register(file: DeviceFile, initial: Record<string, unknown> = {}): Runtime {
    const id = deviceId(file);
    if (this.devices.has(id)) throw new KernelError("value", `A device with id '${id}' is already registered.`);
    const names = channelNames(file);
    const runtime: Runtime = {
      file,
      values: defaultValues(file, initial),
      connected: false,
      connectedAt: 0,
      faulted: null,
      referenceProblem: null,
      applyingSafeState: false,
      reads: new Map(),
      accepted: new Map(),
      unknownSince: new Map(),
      rules: file.watchdog.max_duration.map((rule) => ({
        rule,
        tree: expr.parseCached(rule.when, names),
        activeSince: null,
        falseSince: null,
        exhausted: false,
        applied: false,
        failures: 0,
        retryAt: 0,
      })),
      runs: new Map(),
    };
    this.devices.set(id, runtime);
    this.orphans.delete(id);
    this.checkReferences();
    return runtime;
  }

  unregister(id: string): void {
    const runtime = this.devices.get(id);
    this.devices.delete(id);
    if (!runtime) return;
    if (fileRefs(runtime.file).some((ref) => ref.device)) this.orphans.set(id, runtime.file);
    this.checkReferences();
  }

  checkReferences(): Record<string, string> {
    const problems: Record<string, string> = {};
    for (const [id, runtime] of this.devices) {
      const missing = [...new Set(fileRefs(runtime.file).map((ref) => ref.device).filter((d): d is string => !!d))]
        .filter((device) => !this.devices.has(device))
        .sort();
      const problem = missing.length ? `its expressions name ${missing.join(", ")}, which isn't registered` : null;
      if (problem) problems[id] = problem;
      runtime.referenceProblem = problem;
    }
    return problems;
  }

  private runtime(id: string): Runtime {
    const runtime = this.devices.get(id);
    if (!runtime) throw new KernelError("lookup", `There is no device '${id}'.`);
    return runtime;
  }


  connect(id: string): void {
    const runtime = this.runtime(id);
    runtime.connected = true;
    runtime.connectedAt = this.clock();
    runtime.faulted = null;
    for (const channel of [...Object.keys(runtime.file.read), ...Object.keys(runtime.file.write)]) {
      markUnknown(runtime, channel, runtime.connectedAt);
    }
    this.snapshot(id);
  }

  snapshot(id: string): void {
    const runtime = this.runtime(id);
    const channels = [
      ...Object.entries(runtime.file.read)
        .filter(([, spec]) => spec.type !== "image")
        .map(([name]) => name),
      ...Object.keys(runtime.file.write),
    ];
    for (const channel of channels) this.noteReading(id, channel, runtime.values[channel], channelUnit(runtime.file, channel));
  }

  noteReading(id: string, channel: string, value: unknown, unit: string | null = null): void {
    const runtime = this.devices.get(id);
    if (!runtime) return;
    const now = this.clock();
    const fileUnit = channelUnit(runtime.file, channel);
    let current = value;
    if (current === null || current === undefined) {
      markUnknown(runtime, channel, now);
      return;
    }
    if (fileUnit && unit && unit !== fileUnit && typeof current === "number") {
      try {
        current = convert(parseQuantity(`${current} ${unit}`), fileUnit);
      } catch (error) {
        if (!(error instanceof UnitError)) throw error;
        markUnknown(runtime, channel, now);
        return;
      }
    }
    if (typeof current === "number" && !Number.isFinite(current)) {
      markUnknown(runtime, channel, now);
      return;
    }
    runtime.reads.set(channel, { value: current, at: now, commanded: false });
  }

  read(id: string, channel: string): unknown {
    const runtime = this.runtime(id);
    if (!(channel in runtime.file.read) && !(channel in runtime.file.write)) {
      throw new KernelError("lookup", `${id} has no channel '${channel}'.`);
    }
    const reason = availability(runtime);
    if (reason) throw new KernelError("value", `${id} is ${reason}.`);
    this.noteReading(id, channel, runtime.values[channel], channelUnit(runtime.file, channel));
    return runtime.values[channel];
  }

  latestValue(id: string, channel: string): unknown {
    const runtime = this.devices.get(id);
    if (!runtime) return null;
    const sample = latest(runtime, channel, this.clock());
    return sample === null ? null : sample.value;
  }

  connectionLost(id: string): DeviceStopResult | null {
    const runtime = this.runtime(id);
    runtime.connected = false;
    const onLoss = runtime.file.watchdog.on_loss ?? (runtime.file.safe_state.length ? "safe_state" : "hold");
    if (onLoss === "safe_state") return this.applySafeState(runtime, true);
    return null;
  }


  evaluate(command: Command, principal: Principal, shadow: Shadow | null = null, wire = false): Decision {
    return this.decide(command, principal, false, shadow, wire);
  }

  private decide(command: Command, principal: Principal, approved: boolean, shadow: Shadow | null, wire = false): Decision {
    try {
      return this.evaluateChecks(command, principal, approved, shadow, wire);
    } catch (error) {
      if (error instanceof Block) {
        return this.decision("blocked", command, { code: error.code, message: error.message, limit: error.limit });
      }
      return this.decision("blocked", command, {
        code: "internal_error",
        message: `Blocked. The safety kernel hit an unexpected error (${(error as Error).name}). Nothing was sent to the device.`,
      });
    }
  }

  private decision(status: Status, command: Command, fields: Partial<Decision>): Decision {
    return {
      status,
      code: null,
      message: "",
      device: command.device,
      target: target(command),
      value: null,
      unit: null,
      limit: null,
      request_id: null,
      ...fields,
    };
  }

  private checkRuns(runtime: Runtime, action: string, spec: ActionSpec, now: number, shadow: Shadow | null): void {
    const rule = spec.max_runs;
    if (rule === null) return;
    const at = now + (shadow !== null ? shadow.now : 0);
    const times = [...(runtime.runs.get(action) ?? [])];
    if (shadow !== null) times.push(...(shadow.runs?.get(key(deviceId(runtime.file), action)) ?? []).map((offset) => now + offset));
    const recent = times.filter((moment) => at - moment >= 0 && at - moment < rule.per);
    if (recent.length >= rule.count) {
      const wait = Math.max(0, Math.min(...recent) + rule.per - at);
      throw new Block(
        "rate_limited",
        `Blocked. ${action} may run at most ${rule.count} times per ${seconds(rule.per)}. ` +
          `It ran ${recent.length} times in that window. Try again in ${seconds(wait)}.`,
        { runs: rule.count, per_s: rule.per },
      );
    }
  }

  private evaluateChecks(command: Command, principal: Principal, approved: boolean, shadow: Shadow | null, wire = false): Decision {
    const now = this.clock();
    const runtime = this.devices.get(command.device);
    if (!runtime) throw new Block("unknown_target", `Blocked. There is no device ${pyStrRepr(command.device)}. Run openhal devices.`);
    const file = runtime.file;
    let spec: WriteChannel | null = null;
    let actionSpec: ActionSpec | null = null;
    if (command.kind === "write") {
      spec = file.write[command.channel] ?? null;
      if (spec === null) {
        const known = Object.keys(file.write).sort().join(", ") || "none";
        throw new Block("unknown_target", `Blocked. ${command.device} has no write channel ${pyStrRepr(command.channel)}. Write channels are ${known}.`);
      }
    } else {
      actionSpec = file.actions[command.action] ?? null;
      if (actionSpec === null) {
        const known = Object.keys(file.actions).sort().join(", ") || "none";
        throw new Block("unknown_target", `Blocked. ${command.device} has no action ${pyStrRepr(command.action)}. Actions are ${known}.`);
      }
      const unknown = Object.keys(command.args).filter((name) => !(name in actionSpec!.args)).sort();
      const missing = Object.keys(actionSpec.args).filter((name) => !(name in command.args)).sort();
      if (unknown.length || missing.length) {
        const parts: string[] = [];
        if (unknown.length) parts.push(`unknown arguments ${unknown.join(", ")}`);
        if (missing.length) parts.push(`missing arguments ${missing.join(", ")}`);
        throw new Block("bad_request", `Blocked. ${command.action} has ${parts.join(" and ")}.`);
      }
    }
    if (this.stopped) throw new Block("stopped", "Blocked. The hub is stopped. A human must unlock it before anything can move.");
    if (!writable(file)) {
      throw new Block(
        "read_only_file",
        `Blocked. ${command.device} is read-only until a human confirms limits for ${unconfirmed(file).join(", ")}. Run the limits interview.`,
      );
    }
    const dangling = [...this.devices.entries()]
      .filter(([, item]) => item.referenceProblem)
      .map(([id, item]) => `${id} (${item.referenceProblem})`);
    if (dangling.length) {
      throw new Block(
        "misconfigured",
        "Blocked. An interlock or condition names a device that isn't registered, so no device can be " +
          `written until it is fixed. ${dangling.join("; ")}.`,
      );
    }
    const reason = availability(runtime);
    if (reason) throw new Block("device_unavailable", `Blocked. ${command.device} is ${reason}.`);
    const hazard = effectiveHazard(file);
    if (principal.kind === "system") throw new Block("not_permitted", "Blocked. The system principal is internal to the kernel.");
    if (principal.kind === "agent" && principal.scope === "read") {
      throw new Block("not_permitted", "Blocked. This client has a read-only token. Ask the owner for a control token.");
    }
    if (!covers(principal, hazard)) {
      throw new Block("not_permitted", `Blocked. ${command.device} is ${hazard} hazard and this client's ${principal.scope} scope doesn't cover it.`);
    }
    let value: unknown;
    let changes: Map<string, unknown>;
    if (command.kind === "write") {
      const tightened = this.sessionLimits.get(key(label(principal), command.device, command.channel));
      value = normalize(command.channel, spec!, command.value, { unit: command.unit ?? null, text: !wire, tightened });
      changes = new Map([[command.channel, value]]);
    } else {
      const args: Record<string, unknown> = {};
      for (const [name, raw] of Object.entries(command.args)) args[name] = normalize(name, actionSpec!.args[name], raw, { text: !wire, argument: true });
      value = args;
      changes = new Map(actionSpec!.effects.map((effect) => [effect, UNKNOWN]));
      this.checkRuns(runtime, command.action, actionSpec!, now, shadow);
    }
    if (command.kind === "write" && spec!.type === "number") {
      const limits = effectiveLimits(spec!, this.sessionLimits.get(key(label(principal), command.device, command.channel)));
      if (limits.rate !== null) {
        const [reference, elapsed] = this.rateReference(runtime, command.channel, spec!, now, shadow);
        if (reference === null) {
          throw new Block(
            "rate_limited",
            `Blocked. ${command.channel} is rate limited and its current value is unknown. Read it first so the change can be measured.`,
          );
        }
        checkRate(command.channel, spec!.unit as string, limits.rate, value as number, reference, elapsed);
      }
    }
    const resolver = this.resolver(runtime, changes, now, shadow);
    if (command.kind === "action") {
      for (const [condition, message] of conditions(actionSpec!)) {
        const result = expr.evaluate(expr.parseCached(condition, channelNames(file)), resolver);
        if (result !== true) {
          const held = result === null ? "is unknown" : "doesn't hold";
          const detail = message ? `${message.slice(0, 1).toUpperCase()}${message.slice(1)}. ` : "";
          const reason = result === false ? message : `${command.action} needs ${condition}, which is unknown`;
          throw new Block(
            "interlock",
            `Blocked. ${detail}${command.action} needs ${condition}, which ${held} right now.`,
            reason ? { interlock: reason } : null,
          );
        }
      }
    }
    this.checkInterlocks(command.device, new Set(changes.keys()), resolver, shadow);
    for (const state of runtime.rules) {
      if (!state.exhausted) continue;
      const mentioned = expr.references(state.tree).filter((ref) => ref.device === null).map((ref) => ref.name);
      if (mentioned.some((name) => changes.has(name)) && expr.evaluate(state.tree, resolver) !== false) {
        throw new Block("duration_exceeded", `Blocked. ${state.rule.when} already ran for its ${seconds(state.rule.for_)} limit. Wait for the budget to reset.`);
      }
    }
    const fields = { value, unit: spec !== null ? spec.unit : null };
    let tier = spec !== null ? spec.confirm : actionSpec!.confirm;
    if (hazard === "high") tier = "confirm-each-time";
    if (this.confirmationSatisfied(command, principal, runtime, tier, value, approved, now)) {
      return this.decision("allowed", command, { ...fields, message: "Allowed." });
    }
    if (principal.kind === "routine") {
      throw new Block("needs_confirmation", `Blocked. ${target(command)} on ${command.device} needs a human to confirm, and routines can't wait for one.`);
    }
    return this.decision("needs_confirmation", command, {
      ...fields,
      code: "needs_confirmation",
      message: `Waiting for a human to approve ${target(command)} on ${command.device}.`,
    });
  }

  private confirmationSatisfied(
    command: Command,
    principal: Principal,
    runtime: Runtime,
    tier: string,
    value: unknown,
    approved: boolean,
    now: number,
  ): boolean {
    if (principal.kind === "human" || approved) return true;
    if (principal.kind === "routine") {
      if (effectiveHazard(runtime.file) === "high") return false;
      return tier === "none";
    }
    if (tier === "none") return true;
    if (tier === "confirm") {
      const expires = this.approvalWindows.get(key(label(principal), command.device, target(command), JSON.stringify(value)));
      return expires !== undefined && now <= expires;
    }
    return false;
  }

  private rateReference(runtime: Runtime, channel: string, spec: WriteChannel, now: number, shadow: Shadow | null): [number | null, number] {
    const id = deviceId(runtime.file);
    if (shadow !== null && shadow.values.has(key(id, channel))) {
      const k = key(id, channel);
      return [Number(shadow.values.get(k)), shadow.now - (shadow.stamps.get(k) ?? shadow.now)];
    }
    const candidates = knownSamples(runtime, channel).filter((sample) => typeof sample.value === "number");
    if (candidates.length) {
      const newest = newestOf(candidates);
      return [newest.value as number, now - newest.at];
    }
    const since = runtime.unknownSince.get(channel);
    if (since !== undefined && since > runtime.connectedAt) return [null, 0];
    let fallback = safeValue(runtime.file, channel);
    if (fallback === null) fallback = spec.min;
    return [fallback, now - runtime.connectedAt];
  }

  private resolver(runtime: Runtime, changes: Map<string, unknown>, now: number, shadow: Shadow | null): expr.Resolver {
    return (ref) => {
      const targetRuntime = ref.device === null ? runtime : this.devices.get(ref.device);
      if (!targetRuntime) return null;
      const id = deviceId(targetRuntime.file);
      let raw: unknown;
      if (targetRuntime === runtime && changes.has(ref.name)) raw = changes.get(ref.name);
      else if (shadow !== null && shadow.values.has(key(id, ref.name))) raw = shadow.values.get(key(id, ref.name));
      else {
        const sample = latest(targetRuntime, ref.name, now);
        raw = sample === null ? null : sample.value;
      }
      return asValue(targetRuntime, ref.name, raw);
    };
  }

  private checkInterlocks(device: string, changed: Set<string>, resolver: expr.Resolver, shadow: Shadow | null): void {
    const owners: Array<[string, DeviceFile, Runtime | null]> = [
      ...[...this.devices.entries()].map(([id, runtime]) => [id, runtime.file, runtime] as [string, DeviceFile, Runtime]),
      ...[...this.orphans.entries()].map(([id, file]) => [id, file, null] as [string, DeviceFile, null]),
    ];
    for (const [ownerId, file, owner] of owners) {
      const names = channelNames(file);
      for (const interlock of file.interlocks) {
        const ifTree = expr.parseCached(interlock.if_, names);
        const requireTree = expr.parseCached(interlock.require, names);
        const refs = [...expr.references(ifTree), ...expr.references(requireTree)];
        const touches = refs.some(
          (ref) => (ref.device === null && ownerId === device && changed.has(ref.name)) || (ref.device === device && changed.has(ref.name)),
        );
        if (!touches) continue;
        const local = ownerId === device ? resolver : this.foreignResolver(owner, device, resolver, shadow);
        const applies = expr.evaluate(ifTree, local);
        const satisfied = expr.evaluate(requireTree, local);
        if (applies !== false && satisfied !== true) {
          const detail = interlock.message ?? `When ${interlock.if_}, ${interlock.require} must hold.`;
          const state = satisfied === null ? "is unknown" : "doesn't hold";
          const where = owner !== null ? ownerId : `${ownerId} (not registered right now)`;
          const reason = satisfied === false ? interlock.message : `${interlock.require} is unknown right now`;
          throw new Block(
            "interlock",
            `Blocked by an interlock on ${where}. ${detail} Right now ${interlock.require} ${state}.`,
            reason ? { interlock: reason } : null,
          );
        }
      }
    }
  }

  private foreignResolver(owner: Runtime | null, changedDevice: string, resolver: expr.Resolver, shadow: Shadow | null): expr.Resolver {
    return (ref) => {
      if (ref.device === null) {
        if (owner === null) return null;
        const id = deviceId(owner.file);
        if (shadow !== null && shadow.values.has(key(id, ref.name))) return asValue(owner, ref.name, shadow.values.get(key(id, ref.name)));
        const sample = latest(owner, ref.name, this.clock());
        return asValue(owner, ref.name, sample === null ? null : sample.value);
      }
      if (ref.device === changedDevice) return resolver({ kind: "ref", device: null, name: ref.name });
      return resolver(ref);
    };
  }


  execute(command: Command, principal: Principal, request: Request | null = null, wire = false): Decision {
    const runtime = this.devices.get(command.device);
    if (!runtime) return this.evaluate(command, principal, null, wire);
    const approved =
      request !== null &&
      this.requests.get(request.requestId) === request &&
      request.status === "approved" &&
      JSON.stringify(request.command) === JSON.stringify(command) &&
      label(request.principal) === label(principal);
    const decision = this.decide(command, principal, approved, null, wire);
    if (decision.status === "needs_confirmation") {
      const queued = this.queueAdd(command, principal, decision);
      if (typeof queued === "string") return { ...decision, status: "blocked", code: "queue_full", message: queued };
      return { ...decision, status: "pending", request_id: queued.requestId };
    }
    if (decision.status !== "allowed") return decision;
    return this.run(runtime, command, principal, decision);
  }

  private run(runtime: Runtime, command: Command, principal: Principal, decision: Decision): Decision {
    const id = deviceId(runtime.file);
    if (command.kind === "write") {
      const value = normalize(command.channel, runtime.file.write[command.channel], command.value, {
        unit: command.unit ?? null,
        tightened: this.sessionLimits.get(key(label(principal), command.device, command.channel)),
      });
      runtime.values[command.channel] = value;
      runtime.accepted.set(command.channel, { value, at: this.clock(), commanded: true });
      runtime.unknownSince.delete(command.channel);
      this.noteReading(id, command.channel, value, channelUnit(runtime.file, command.channel));
      return { ...decision, status: "done", message: `Done. ${command.channel} is now ${display(value, decision.unit)}.` };
    }
    const spec = runtime.file.actions[command.action];
    const args: Record<string, unknown> = {};
    for (const [name, raw] of Object.entries(command.args)) args[name] = normalize(name, spec.args[name], raw, { argument: true });
    const runs = runtime.runs.get(command.action) ?? [];
    runs.push(this.clock());
    runtime.runs.set(command.action, runs);
    const effects = spec.effects;
    for (const channel of effects) markUnknown(runtime, channel, this.clock());
    for (const channel of effects) this.noteReading(id, channel, runtime.values[channel], channelUnit(runtime.file, channel));
    return { ...decision, status: "done", value: args, message: `Done. ${command.action} ran.` };
  }

  dryRun(commands: Command[], principal: Principal, wire = false): Decision[] {
    const shadow: Shadow = { values: new Map(), stamps: new Map(), now: 0, runs: new Map() };
    return commands.map((command) => {
      const decision = this.evaluate(command, principal, shadow, wire);
      if (decision.status === "allowed" || decision.status === "needs_confirmation") {
        if (command.kind === "write") {
          shadow.values.set(key(command.device, command.channel), decision.value);
          shadow.stamps.set(key(command.device, command.channel), shadow.now);
        } else {
          const runKey = key(command.device, command.action);
          shadow.runs!.set(runKey, [...(shadow.runs!.get(runKey) ?? []), shadow.now]);
        }
      }
      return decision;
    });
  }


  private queueAdd(command: Command, principal: Principal, decision: Decision): Request | string {
    const now = this.clock();
    this.expire(now);
    const pending = [...this.requests.values()].filter((request) => request.status === "pending");
    const mine = pending.filter((request) => label(request.principal) === label(principal));
    if (mine.length >= 20) {
      return `This client already has ${mine.length} requests waiting for a human. Wait for them to be decided.`;
    }
    if (pending.length >= 100) return "The confirmation queue is full. Wait for pending requests to be decided.";
    this.requestCounter += 1;
    const request: Request = {
      requestId: `demo-${String(this.requestCounter).padStart(4, "0")}`,
      command,
      principal,
      createdAt: now,
      expiresAt: now + this.confirmTtlS,
      dryRun: decision,
      status: "pending",
      decidedBy: null,
      result: null,
    };
    this.requests.set(request.requestId, request);
    return request;
  }

  expire(now = this.clock()): void {
    for (const request of this.requests.values()) {
      if (request.status === "pending" && now > request.expiresAt) request.status = "expired";
    }
  }

  pending(): Request[] {
    this.expire();
    return [...this.requests.values()].filter((request) => request.status === "pending").sort((a, b) => a.createdAt - b.createdAt);
  }

  confirm(requestId: string, principal: Principal): Decision {
    const request = this.requests.get(requestId);
    if (principal.kind !== "human") throw new KernelError("permission", "Approving a request takes a human principal.");
    this.expire();
    if (!request || request.status !== "pending") {
      throw new KernelError("lookup", `Request ${requestId} is ${request ? request.status : "missing"}, so it can't be approved.`);
    }
    request.status = "approved";
    request.decidedBy = label(principal);
    const stoppedBefore = this.stopped;
    const decision = this.execute(request.command, request.principal, request);
    request.result = decision;
    request.status = decision.status === "done" ? "done" : decision.status === "failed" ? "failed" : "blocked";
    if (decision.status === "done" && !stoppedBefore && !this.stopped) {
      const runtime = this.devices.get(request.command.device)!;
      const command = request.command;
      const tier = command.kind === "write" ? runtime.file.write[command.channel].confirm : runtime.file.actions[command.action].confirm;
      if (tier === "confirm" && effectiveHazard(runtime.file) !== "high") {
        this.approvalWindows.set(
          key(label(request.principal), command.device, target(command), JSON.stringify(decision.value)),
          this.clock() + APPROVAL_WINDOW_S,
        );
      }
    }
    return decision;
  }

  reject(requestId: string, principal: Principal): Request {
    if (principal.kind !== "human") throw new KernelError("permission", "Rejecting a request takes a human principal.");
    const request = this.requests.get(requestId);
    if (!request || request.status !== "pending") throw new KernelError("lookup", `Request ${requestId} is not pending.`);
    request.status = "rejected";
    request.decidedBy = label(principal);
    return request;
  }


  tighten(principal: Principal, id: string, channel: string, limits: { min?: unknown; max?: unknown; rate?: unknown }): Tightened {
    const runtime = this.devices.get(id);
    if (!runtime) throw new KernelError("lookup", `There is no device '${id}'.`);
    const spec = runtime.file.write[channel];
    if (!spec || spec.type !== "number" || spec.unit === null) {
      throw new KernelError("lookup", `Refused. ${id} has no numeric write channel ${pyStrRepr(channel)}.`);
    }
    const k = key(label(principal), id, channel);
    const current = effectiveLimits(spec, this.sessionLimits.get(k));
    const updated: Tightened = { ...(this.sessionLimits.get(k) ?? {}) };
    try {
      if (limits.min !== undefined && limits.min !== null) {
        const low = convert(parseQuantity(limits.min), spec.unit);
        if (low < current.min) {
          throw new Block("cannot_loosen", `Refused. ${channel} min is already ${formatQuantity(current.min, spec.unit)}. Session limits can only be tightened.`);
        }
        updated.min = low;
      }
      if (limits.max !== undefined && limits.max !== null) {
        const high = convert(parseQuantity(limits.max), spec.unit);
        if (high > current.max) {
          throw new Block("cannot_loosen", `Refused. ${channel} max is already ${formatQuantity(current.max, spec.unit)}. Session limits can only be tightened.`);
        }
        updated.max = high;
      }
      if (limits.rate !== undefined && limits.rate !== null) {
        const value = parseRate(limits.rate, spec.unit);
        if (current.rate !== null && value > current.rate) {
          throw new Block(
            "cannot_loosen",
            `Refused. ${channel} may already change by at most ${formatQuantity(current.rate, spec.unit)} per second. Session limits can only be tightened.`,
          );
        }
        updated.rate = value;
      }
    } catch (error) {
      if (error instanceof UnitError) throw new Block("bad_unit", `Refused. ${error.message}`);
      throw error;
    }
    if ((updated.min ?? -Infinity) > (updated.max ?? Infinity)) throw new Block("cannot_loosen", "Refused. min would be above max.");
    this.sessionLimits.set(k, updated);
    return updated;
  }


  stopAll(_principal: Principal, reason = "stop requested"): { reason: string; devices: DeviceStopResult[]; cancelled: number } {
    this.stopped = true;
    this.stopReason = reason;
    let cancelled = 0;
    for (const request of this.requests.values()) {
      if (request.status === "pending") {
        request.status = "cancelled";
        cancelled += 1;
      }
    }
    this.approvalWindows.clear();
    const devices = [...this.devices.values()].map((runtime) => this.applySafeState(runtime, false, reason));
    return { reason, devices, cancelled };
  }

  private applySafeState(runtime: Runtime, allowDisconnected: boolean, reason = "stop requested"): DeviceStopResult {
    const file = runtime.file;
    const id = deviceId(file);
    if (!Object.keys(file.write).length && !Object.keys(file.actions).length) return { device: id, status: "safe", detail: "read-only device" };
    if (!file.safe_state.length) return { device: id, status: "no_safe_state", detail: file.safe_state_note ?? "no safe state defined" };
    if (!runtime.connected && !allowDisconnected) return { device: id, status: "failed", detail: "not connected" };
    const errors: string[] = [];
    let steps = 1;
    for (const step of file.safe_state) {
      if (step.action !== null) {
        steps += 1;
        try {
          const spec = file.actions[step.action];
          for (const [name, raw] of Object.entries(step.args)) normalize(name, spec.args[name], quantityText(raw, spec.args[name].unit));
        } catch (error) {
          errors.push(`${step.action}: ${(error as Error).message}`);
        }
      }
      for (const [channel, raw] of Object.entries(step.values)) {
        steps += 1;
        try {
          const value = safeValueFor(file, channel, raw);
          runtime.values[channel] = value;
          runtime.accepted.set(channel, { value, at: this.clock(), commanded: true });
          runtime.unknownSince.delete(channel);
        } catch (error) {
          errors.push(`${channel}: ${(error as Error).message}`);
          markUnknown(runtime, channel, this.clock());
        }
      }
    }
    if (!errors.length) return { device: id, status: "safe", detail: reason };
    return { device: id, status: errors.length >= steps ? "failed" : "partial", detail: errors.join("; ") };
  }

  unlock(principal: Principal, phrase: string): void {
    if (principal.kind !== "human") throw new KernelError("permission", "Unlocking the hub after a stop takes a human principal.");
    if (phrase.trim().toLowerCase() !== UNLOCK_PHRASE) throw new KernelError("value", `Type ${UNLOCK_PHRASE} to confirm.`);
    this.stopped = false;
    this.stopReason = null;
    this.approvalWindows.clear();
  }


  tick(): string[] {
    const fired: string[] = [];
    const now = this.clock();
    for (const [id, runtime] of this.devices) {
      const resolver = this.resolver(runtime, new Map(), now, null);
      for (const state of runtime.rules) {
        const active = expr.evaluate(state.tree, resolver);
        const counting = active === true || (active === null && state.activeSince !== null);
        if (counting) {
          state.falseSince = null;
          if (state.activeSince === null) state.activeSince = now;
          if (!state.exhausted && now - state.activeSince >= state.rule.for_) {
            state.exhausted = true;
            state.applied = false;
            state.failures = 0;
            state.retryAt = now;
            fired.push(`${id}: ${state.rule.when}`);
          }
          if (state.exhausted && !state.applied && now >= state.retryAt) this.fire(runtime, state, now);
        } else if (active === false) {
          if (state.falseSince === null) state.falseSince = now;
          const resetAfter = state.rule.reset_after ?? state.rule.for_;
          if (now - state.falseSince >= resetAfter) {
            state.activeSince = null;
            state.exhausted = false;
            state.applied = false;
          }
        }
      }
    }
    return fired;
  }

  private fire(runtime: Runtime, state: RuleState, now: number): void {
    const escalate = state.rule.then !== "safe_state" && state.failures >= WATCHDOG_MAX_FAILURES;
    let ok: boolean;
    if (escalate || state.rule.then === "safe_state") {
      ok = this.applySafeState(runtime, false, `watchdog: ${state.rule.when}`).status === "safe";
    } else {
      ok = true;
      for (const [channel, raw] of Object.entries(state.rule.then)) {
        try {
          const value = safeValueFor(runtime.file, channel, raw);
          runtime.values[channel] = value;
          runtime.accepted.set(channel, { value, at: this.clock(), commanded: true });
          runtime.unknownSince.delete(channel);
        } catch {
          ok = false;
          markUnknown(runtime, channel, this.clock());
        }
      }
    }
    if (ok) state.applied = true;
    else {
      state.failures += 1;
      state.retryAt = now + Math.min(2 ** state.failures, 30);
    }
  }
}

export { Block, UNKNOWN };
