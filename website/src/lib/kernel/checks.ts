import type { ArgSpec, WriteChannel } from "./model";
import { formatF, isClose, pyFloatRepr, pyRound, pyStrRepr } from "./pyformat";
import { UnitError, convert, formatQuantity, normalizeUnit, parseQuantity, splitQuantity } from "./units";

export class Block extends Error {
  constructor(
    public code: string,
    message: string,
    public limit: Record<string, unknown> | null = null,
  ) {
    super(message);
  }
}

export interface Limits {
  min: number;
  max: number;
  rate: number | null;
}

export type Tightened = Partial<Record<"min" | "max" | "rate", number>>;

function isWriteChannel(spec: WriteChannel | ArgSpec): spec is WriteChannel {
  return "max_change_per_s" in spec;
}

export function effectiveLimits(spec: WriteChannel | ArgSpec, tightened?: Tightened | null): Limits {
  let low = spec.min as number;
  let high = spec.max as number;
  let rate = isWriteChannel(spec) ? spec.max_change_per_s : null;
  if (tightened && Object.keys(tightened).length) {
    low = Math.max(low, tightened.min ?? low);
    high = Math.min(high, tightened.max ?? high);
    if (tightened.rate !== undefined) rate = rate === null ? tightened.rate : Math.min(rate, tightened.rate);
  }
  return { min: low, max: high, rate };
}

function pyRawText(raw: number | bigint): string {
  if (typeof raw === "bigint") return raw.toString();
  return Number.isInteger(raw) ? String(raw) : pyFloatRepr(raw);
}

export interface NormalizeOptions {
  unit?: string | null;
  text?: boolean;
  tightened?: Tightened | null;
  argument?: boolean;
}

function jsonNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : pyFloatRepr(value);
}

function quantityJson(quantity: { value: number; unit: string }): string {
  return `{"value": ${jsonNumber(quantity.value)}, "unit": ${JSON.stringify(quantity.unit)}}`;
}

export function shaped(name: string, spec: WriteChannel | ArgSpec, raw: unknown, unit: string | null = null, text = true): unknown {
  if (unit !== null) {
    if (spec.type !== "number") throw new Block("bad_unit", `${name} takes a ${spec.type} value with no unit.`);
    if (typeof raw !== "number") throw new Block("bad_unit", `${name} has a unit, so its value must be a number, not ${reprOf(raw)}.`);
    return { value: raw, unit };
  }
  if (!text && spec.type === "number" && typeof raw === "string") {
    const example = splitQuantity(raw) ?? { value: 1, unit: normalizeUnit(spec.unit ?? "") === "percent" ? "%" : (spec.unit ?? "") };
    throw new Block("bad_unit", `${name} needs its number and unit apart, as ${quantityJson(example)}, not the text ${pyStrRepr(raw)}.`, {
      expected: example,
    });
  }
  return raw;
}

function reprOf(raw: unknown): string {
  if (typeof raw === "string") return pyStrRepr(raw);
  if (typeof raw === "boolean") return raw ? "True" : "False";
  if (raw === null || raw === undefined) return "None";
  return String(raw);
}

export function normalize(name: string, spec: WriteChannel | ArgSpec, raw: unknown, options: NormalizeOptions = {}): number | boolean | string {
  try {
    return normalizeShaped(name, spec, shaped(name, spec, raw, options.unit ?? null, options.text ?? true), options.tightened);
  } catch (error) {
    if (options.argument && error instanceof Block) {
      throw new Block(error.code, error.message, error.limit !== null ? { ...error.limit, argument: name } : { argument: name });
    }
    throw error;
  }
}

function normalizeShaped(name: string, spec: WriteChannel | ArgSpec, raw: unknown, tightened?: Tightened | null): number | boolean | string {
  if (spec.type === "bool") {
    if (typeof raw !== "boolean") throw new Block("bad_value", `${name} needs true or false.`);
    return raw;
  }
  if (spec.type === "enum") {
    if (typeof raw !== "string" || !spec.values.includes(raw)) {
      throw new Block("bad_value", `${name} must be one of ${spec.values.join(", ")}.`, { values: spec.values });
    }
    return raw;
  }
  if (spec.type === "string") {
    if (typeof raw !== "string") throw new Block("bad_value", `${name} needs text.`);
    if (raw.length > (spec.max_length ?? 0)) throw new Block("bad_value", `${name} may be at most ${spec.max_length} characters.`);
    if (spec.pattern !== null) {
      let matched: boolean;
      try {
        matched = new RegExp(`^(?:${spec.pattern})$`, "u").test(raw);
      } catch {
        matched = false;
      }
      if (!matched) throw new Block("bad_value", `${name} doesn't match the allowed pattern.`);
    }
    return raw;
  }
  return number(name, spec, raw, tightened);
}

function number(name: string, spec: WriteChannel | ArgSpec, raw: unknown, tightened?: Tightened | null): number {
  const unit = spec.unit as string;
  const isNumber = typeof raw === "number" || typeof raw === "bigint";
  const isMapping = raw !== null && typeof raw === "object" && !Array.isArray(raw);
  if (typeof raw === "boolean" || !(typeof raw === "string" || isMapping || isNumber)) {
    throw new Block("bad_unit", `${name} needs a number with a unit, for example ${formatQuantity(1, unit)}.`);
  }
  if (isNumber) {
    const value = raw as number | bigint;
    throw new Block("bad_unit", `${name} needs a unit. Send ${formatQuantity(Number(value), unit)} rather than ${pyRawText(value)}.`);
  }
  let value: number;
  try {
    value = convert(parseQuantity(raw), unit);
  } catch (error) {
    if (error instanceof UnitError) throw new Block("bad_unit", `${name}: ${error.message}`);
    throw error;
  }
  const limits = effectiveLimits(spec, tightened);
  const asked = formatQuantity(value, unit);
  if (value < limits.min && !isClose(value, limits.min, 1e-12, 1e-12)) {
    throw new Block("below_min", `Blocked. The ${name} limit is ${formatQuantity(limits.min, unit)} (min). Requested ${asked}.`, {
      min: limits.min,
      unit,
    });
  }
  if (value > limits.max && !isClose(value, limits.max, 1e-12, 1e-12)) {
    throw new Block("above_max", `Blocked. The ${name} limit is ${formatQuantity(limits.max, unit)} (max). Requested ${asked}.`, {
      max: limits.max,
      unit,
    });
  }
  if (spec.step !== null) {
    const base = spec.min || 0;
    const steps = (value - base) / spec.step;
    if (!isClose(steps, pyRound(steps), 0, 1e-6)) {
      throw new Block(
        "bad_step",
        `Blocked. ${name} moves in steps of ${formatQuantity(spec.step, unit)} from ${formatQuantity(base, unit)}. Requested ${asked}.`,
        { step: spec.step, unit },
      );
    }
  }
  return value;
}

export function checkRate(name: string, unit: string, rate: number | null, next: number, reference: number | null, elapsedS: number): void {
  if (rate === null || reference === null) return;
  const elapsed = Math.min(Math.max(elapsedS, 0), 3600);
  const allowed = rate * elapsed;
  const change = Math.abs(next - reference);
  if (change > allowed && !isClose(change, allowed, 1e-9, 1e-9)) {
    const low = reference - allowed;
    const high = reference + allowed;
    const wait = (change - allowed) / rate;
    throw new Block(
      "rate_limited",
      `Blocked. ${name} may change by ${formatQuantity(rate, unit)} per second. ` +
        `Right now it can go from ${formatQuantity(low, unit)} to ${formatQuantity(high, unit)}. ` +
        `Requested ${formatQuantity(next, unit)}, which is possible in ${formatF(wait, 1)} s, or use small steps.`,
      { rate_per_s: rate, unit, from: low, to: high, wait_s: wait },
    );
  }
}
