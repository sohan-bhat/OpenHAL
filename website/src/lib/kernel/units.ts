import { formatG, pyFloatRepr, pyStrRepr } from "./pyformat";

export class UnitError extends Error {}

type Dims = Record<string, number>;

interface Base {
  name: string;
  symbol: string;
  dims: Dims;
  scale: number;
  offset?: number;
  prefixable?: boolean;
}

const L: Dims = { length: 1 };
const M: Dims = { mass: 1 };
const T: Dims = { time: 1 };
const I: Dims = { current: 1 };
const K: Dims = { temperature: 1 };
const POWER: Dims = { mass: 1, length: 2, time: -3 };
const ENERGY: Dims = { mass: 1, length: 2, time: -2 };
const VOLT: Dims = { mass: 1, length: 2, time: -3, current: -1 };
const OHM: Dims = { mass: 1, length: 2, time: -3, current: -2 };
const PRESSURE: Dims = { mass: 1, length: -1, time: -2 };
const FORCE: Dims = { mass: 1, length: 1, time: -2 };

const BASES: Array<[string[], Base]> = [
  [["dimensionless"], { name: "dimensionless", symbol: "", dims: {}, scale: 1 }],
  [["count"], { name: "count", symbol: "count", dims: {}, scale: 1 }],
  [["percent"], { name: "percent", symbol: "%", dims: {}, scale: 0.01 }],
  [["ppm"], { name: "ppm", symbol: "ppm", dims: {}, scale: 1e-6 }],
  [["radian", "radians", "rad"], { name: "radian", symbol: "rad", dims: {}, scale: 1, prefixable: true }],
  [["degree", "degrees", "deg", "arcdeg"], { name: "degree", symbol: "deg", dims: {}, scale: Math.PI / 180 }],
  [["rpm", "revolutions_per_minute"], { name: "revolutions_per_minute", symbol: "rpm", dims: { time: -1 }, scale: (2 * Math.PI) / 60 }],
  [["kelvin", "K", "degK"], { name: "kelvin", symbol: "K", dims: K, scale: 1, offset: 0, prefixable: true }],
  [["degree_Celsius", "degC", "celsius", "°C", "degreeC"], { name: "degree_Celsius", symbol: "°C", dims: K, scale: 1, offset: 273.15 }],
  [["degree_Fahrenheit", "degF", "fahrenheit", "°F", "degreeF"], { name: "degree_Fahrenheit", symbol: "°F", dims: K, scale: 5 / 9, offset: 233.15 + 200 / 9 }],
  [["delta_degree_Celsius", "delta_degC", "Δcelsius"], { name: "delta_degree_Celsius", symbol: "Δ°C", dims: K, scale: 1 }],
  [["delta_degree_Fahrenheit", "delta_degF", "Δfahrenheit"], { name: "delta_degree_Fahrenheit", symbol: "Δ°F", dims: K, scale: 5 / 9 }],
  [["second", "seconds", "s", "sec"], { name: "second", symbol: "s", dims: T, scale: 1, prefixable: true }],
  [["minute", "minutes", "min"], { name: "minute", symbol: "min", dims: T, scale: 60 }],
  [["hour", "hours", "h", "hr"], { name: "hour", symbol: "h", dims: T, scale: 3600 }],
  [["day", "days", "d"], { name: "day", symbol: "d", dims: T, scale: 86400 }],
  [["hertz", "Hz"], { name: "hertz", symbol: "Hz", dims: { time: -1 }, scale: 1, prefixable: true }],
  [["meter", "metre", "meters", "metres", "m"], { name: "meter", symbol: "m", dims: L, scale: 1, prefixable: true }],
  [["gram", "grams", "g"], { name: "gram", symbol: "g", dims: M, scale: 1, prefixable: true }],
  [["liter", "litre", "liters", "litres", "l", "L"], { name: "liter", symbol: "l", dims: { length: 3 }, scale: 0.001, prefixable: true }],
  [["ampere", "amperes", "amp", "amps", "A"], { name: "ampere", symbol: "A", dims: I, scale: 1, prefixable: true }],
  [["volt", "volts", "V"], { name: "volt", symbol: "V", dims: VOLT, scale: 1000, prefixable: true }],
  [["watt", "watts", "W"], { name: "watt", symbol: "W", dims: POWER, scale: 1000, prefixable: true }],
  [["watt_hour", "Wh"], { name: "watt_hour", symbol: "Wh", dims: ENERGY, scale: 3600 * 1000, prefixable: true }],
  [["joule", "joules", "J"], { name: "joule", symbol: "J", dims: ENERGY, scale: 1000, prefixable: true }],
  [["ohm", "ohms", "Ω"], { name: "ohm", symbol: "Ω", dims: OHM, scale: 1000, prefixable: true }],
  [["newton", "newtons", "N"], { name: "newton", symbol: "N", dims: FORCE, scale: 1000, prefixable: true }],
  [["pascal", "Pa"], { name: "pascal", symbol: "Pa", dims: PRESSURE, scale: 1000, prefixable: true }],
  [["bar"], { name: "bar", symbol: "bar", dims: PRESSURE, scale: 1e8, prefixable: true }],
  [["lux", "lx"], { name: "lux", symbol: "lx", dims: { luminosity: 1, length: -2 }, scale: 1, prefixable: true }],
];

const PREFIXES: Array<[string, string, string, number]> = [
  ["G", "giga", "G", 1e9],
  ["M", "mega", "M", 1e6],
  ["k", "kilo", "k", 1e3],
  ["h", "hecto", "h", 1e2],
  ["c", "centi", "c", 1e-2],
  ["m", "milli", "m", 1e-3],
  ["u", "micro", "µ", 1e-6],
  ["µ", "micro", "µ", 1e-6],
  ["μ", "micro", "µ", 1e-6],
  ["n", "nano", "n", 1e-9],
];

interface Atom {
  name: string;
  symbol: string;
  dims: Dims;
  scale: number;
  offset?: number;
}

const TABLE = new Map<string, Atom>();
for (const [aliases, base] of BASES) {
  for (const alias of aliases) TABLE.set(alias, base);
}
for (const [aliases, base] of BASES) {
  if (!base.prefixable) continue;
  const shortForms = aliases.filter((alias) => alias.length <= 3 && alias === base.symbol);
  for (const [symbol, long, pretty, factor] of PREFIXES) {
    const atom: Atom = { name: `${long}${base.name}`, symbol: `${pretty}${base.symbol}`, dims: base.dims, scale: base.scale * factor };
    for (const alias of shortForms) if (!TABLE.has(`${symbol}${alias}`)) TABLE.set(`${symbol}${alias}`, atom);
    for (const alias of aliases) if (alias.length > 3 && !TABLE.has(`${long}${alias}`)) TABLE.set(`${long}${alias}`, atom);
  }
}

export interface Unit {
  parts: Array<{ atom: Atom; power: number }>;
}

export interface Quantity {
  magnitude: number;
  unit: Unit;
}

const ALIASES: Record<string, string> = { "%": "percent", "%/s": "percent / second" };

export function normalizeUnit(unit: string): string {
  const text = unit.trim();
  if (text in ALIASES) return ALIASES[text];
  return text.replaceAll("%", "percent");
}

function parseUnitExpression(text: string): Unit {
  const tokens = text.match(/\*\*|[()*/^]|[^\s()*/^]+/g) ?? [];
  let pos = 0;
  const peek = () => tokens[pos];
  const fail = (): never => {
    throw new UnitError("bad unit");
  };

  function factor(): Unit {
    const tok = tokens[pos++];
    if (tok === undefined) fail();
    let unit: Unit;
    if (tok === "(") {
      unit = product();
      if (tokens[pos++] !== ")") fail();
    } else {
      const atom = TABLE.get(tok);
      if (!atom) {
        if (/^[0-9.]+$/.test(tok) && tok === "1") return { parts: [] };
        fail();
      }
      unit = { parts: [{ atom: atom!, power: 1 }] };
    }
    if (peek() === "^" || peek() === "**") {
      pos++;
      const exponent = Number(tokens[pos++]);
      if (!Number.isFinite(exponent)) fail();
      unit = { parts: unit.parts.map((part) => ({ atom: part.atom, power: part.power * exponent })) };
    }
    return unit;
  }

  function product(): Unit {
    let unit = factor();
    while (peek() === "*" || peek() === "/") {
      const op = tokens[pos++];
      const next = factor();
      const sign = op === "/" ? -1 : 1;
      unit = { parts: [...unit.parts, ...next.parts.map((part) => ({ atom: part.atom, power: part.power * sign }))] };
    }
    return unit;
  }

  const unit = product();
  if (pos !== tokens.length) fail();
  return unit;
}

export function parseUnit(unit: unknown): Unit {
  if (typeof unit !== "string" || !unit.trim()) {
    throw new UnitError("A unit is required, for example degC, percent or V.");
  }
  try {
    return parseUnitExpression(normalizeUnit(unit));
  } catch {
    throw new UnitError(`Unknown unit ${pyStrRepr(unit)}.`);
  }
}

function dimsOf(unit: Unit): string {
  const total: Dims = {};
  for (const { atom, power } of unit.parts) {
    for (const [dim, exp] of Object.entries(atom.dims)) total[dim] = (total[dim] ?? 0) + exp * power;
  }
  return Object.keys(total)
    .filter((dim) => total[dim] !== 0)
    .sort()
    .map((dim) => `${dim}^${total[dim]}`)
    .join(" ");
}

function rootFactor(unit: Unit): number {
  let factor = 1;
  for (const { atom, power } of unit.parts) factor *= power === 1 ? atom.scale : atom.scale ** power;
  return factor;
}

function offsetAtom(unit: Unit): Atom | null {
  const parts = unit.parts.filter((part) => part.power !== 0);
  if (parts.length === 1 && parts[0].power === 1 && parts[0].atom.offset !== undefined) return parts[0].atom;
  return null;
}

function hasOffsetUnit(unit: Unit): boolean {
  return unit.parts.some((part) => part.atom.offset !== undefined && part.atom.offset !== 0);
}

function finite(value: number, what: string): number {
  if (!Number.isFinite(value)) throw new UnitError(`${what} must be a finite number.`);
  return value;
}

const SUPERSCRIPT: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻",
};

function prettyNumber(magnitude: number): string {
  const text = pyFloatRepr(magnitude);
  const match = /^(-?[0-9.]+)e([+-])([0-9]+)$/.exec(text);
  if (!match) return text;
  const digits = String(Number(match[3]));
  const exponent = `${match[2] === "-" ? "-" : ""}${digits}`;
  return `${match[1]}×10${[...exponent].map((char) => SUPERSCRIPT[char]).join("")}`;
}

function prettyUnit(unit: Unit): string {
  const top = unit.parts.filter((part) => part.power > 0 && part.atom.symbol);
  const bottom = unit.parts.filter((part) => part.power < 0 && part.atom.symbol);
  const show = (part: { atom: Atom; power: number }, power: number) =>
    power === 1 ? part.atom.symbol : `${part.atom.symbol}${[...String(power)].map((char) => SUPERSCRIPT[char]).join("")}`;
  let text = top.map((part) => show(part, part.power)).join("·");
  if (bottom.length) text = `${text || "1"}/${bottom.map((part) => show(part, -part.power)).join("·")}`;
  return text;
}

export function prettyQuantity(quantity: Quantity): string {
  const unit = prettyUnit(quantity.unit);
  return unit ? `${prettyNumber(quantity.magnitude)} ${unit}` : prettyNumber(quantity.magnitude);
}

function quantityOf(magnitude: number, unit: Unit): Quantity {
  return { magnitude, unit };
}

const NUMBER = /^([+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(.*)$/s;

function isPlainNumber(value: unknown): value is number | bigint {
  return typeof value === "bigint" || typeof value === "number";
}

export function parseQuantity(value: unknown, defaultUnit?: string): Quantity {
  if (typeof value === "boolean") throw new UnitError("This value needs a number with a unit, not a boolean.");
  if (isPlainNumber(value)) {
    if (defaultUnit === undefined) throw new UnitError("This value needs a unit, for example 30 degC or 50 %.");
    return quantityOf(finite(Number(value), "Value"), parseUnit(defaultUnit));
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const keys = Object.keys(value);
    if (keys.length !== 2 || !keys.includes("value") || !keys.includes("unit")) {
      throw new UnitError("A quantity mapping must have exactly the keys value and unit.");
    }
    const record = value as { value: unknown; unit: unknown };
    if (typeof record.value === "boolean" || !isPlainNumber(record.value)) {
      throw new UnitError("The value of a quantity must be a number.");
    }
    return quantityOf(finite(Number(record.value), "Value"), parseUnit(record.unit));
  }
  if (typeof value === "string") {
    const text = value.trim();
    const match = NUMBER.exec(text);
    if (!match) throw new UnitError(`Could not read ${pyStrRepr(value)} as a number with a unit.`);
    const [, number, rest] = match;
    let unit = rest;
    if (!unit) {
      if (defaultUnit === undefined) throw new UnitError(`${pyStrRepr(value)} needs a unit, for example ${number} degC.`);
      unit = defaultUnit;
    }
    return quantityOf(finite(Number(number), "Value"), parseUnit(unit));
  }
  throw new UnitError(`This value needs a number with a unit, not ${pyTypeName(value)}.`);
}

function pyTypeName(value: unknown): string {
  if (value === null || value === undefined) return "NoneType";
  if (Array.isArray(value)) return "list";
  if (typeof value === "string") return "str";
  return typeof value;
}

function convertQuantity(quantity: Quantity, target: Unit): number {
  if (dimsOf(quantity.unit) !== dimsOf(target)) throw new Error("dimensionality");
  const source = quantity.unit;
  const srcOffset = offsetAtom(source);
  const dstOffset = offsetAtom(target);
  if ((srcOffset && srcOffset.offset) || (dstOffset && dstOffset.offset)) {
    if (!srcOffset || !dstOffset) throw new Error("offset");
    const reference = quantity.magnitude * srcOffset.scale + (srcOffset.offset ?? 0);
    return (reference - (dstOffset.offset ?? 0)) / dstOffset.scale;
  }
  if (hasOffsetUnit(source) || hasOffsetUnit(target)) throw new Error("offset");
  const factor = rootFactor(source) / rootFactor(target);
  return quantity.magnitude * factor;
}

export function convert(quantity: Quantity, unit: string): number {
  const target = parseUnit(unit);
  let converted: number;
  try {
    converted = convertQuantity(quantity, target);
  } catch {
    throw new UnitError(`${prettyQuantity(quantity)} can't be converted to ${unit}.`);
  }
  return finite(converted, "Converted value");
}

const DELTA: Record<string, string> = {
  degree_Celsius: "delta_degree_Celsius",
  degree_Fahrenheit: "delta_degree_Fahrenheit",
};

function withDeltas(unit: Unit): Unit {
  return {
    parts: unit.parts.map((part) => {
      const delta = DELTA[part.atom.name];
      return delta ? { atom: TABLE.get(delta)!, power: part.power } : part;
    }),
  };
}

function perSecond(channelUnit: string): Unit {
  const unit = withDeltas(parseUnit(channelUnit));
  return { parts: [...unit.parts, { atom: TABLE.get("second")!, power: -1 }] };
}

export function parseRate(value: unknown, channelUnit: string): number {
  if (typeof value === "number" || typeof value === "bigint") return finite(Number(value), "Rate");
  let text = value;
  if (typeof value === "string") text = value.replaceAll("%/s", "percent / second");
  let quantity: Quantity;
  if (typeof text === "string") {
    const match = NUMBER.exec(text.trim());
    if (match && !match[2]) {
      quantity = { magnitude: finite(Number(match[1]), "Value"), unit: perSecond(channelUnit) };
    } else {
      quantity = parseQuantity(text);
    }
  } else {
    quantity = parseQuantity(text);
  }
  return convertRate(quantity, channelUnit);
}

export function convertRate(quantity: Quantity, channelUnit: string): number {
  const target = perSecond(channelUnit);
  const source = { magnitude: quantity.magnitude, unit: withDeltas(quantity.unit) };
  try {
    return finite(convertQuantity(source, target), "Rate");
  } catch (error) {
    if (error instanceof UnitError) throw error;
    throw new UnitError(`${prettyQuantity(source)} is not a rate in ${channelUnit} per second.`);
  }
}

const COMPACT_DURATION = /^\s*([0-9]*\.?[0-9]+)\s*(ms|s|min|h)\s*$/;

export function parseDuration(value: unknown): number {
  let text = value;
  if (typeof value === "string") {
    const compact = COMPACT_DURATION.exec(value);
    if (compact) text = `${compact[1]} ${compact[2]}`;
  }
  if (typeof text === "number" || typeof text === "bigint") {
    throw new UnitError("A duration needs a unit, for example 5 s or 10 min.");
  }
  const seconds = convert(parseQuantity(text), "second");
  if (seconds < 0) throw new UnitError("A duration can't be negative.");
  return seconds;
}

export function formatQuantity(magnitude: number, unit: string): string {
  const shown = normalizeUnit(unit) === "percent" ? "%" : unit;
  return `${formatG(magnitude, 6)} ${shown}`;
}

const QUANTITY_TEXT = /^\s*([-+]?[0-9][0-9.eE+-]{0,30})\s*([^\s0-9].{0,39}?)\s*$/;

export function splitQuantity(text: string): { value: number; unit: string } | null {
  const found = QUANTITY_TEXT.exec(text);
  if (!found) return null;
  if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(found[1])) return null;
  const magnitude = Number(found[1]);
  if (!Number.isFinite(magnitude)) return null;
  return { value: magnitude, unit: found[2] };
}
