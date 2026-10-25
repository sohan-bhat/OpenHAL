const SYMBOLS: Record<string, string> = {
  percent: "%",
  degC: "°C",
  degree_Celsius: "°C",
  degF: "°F",
  degree_Fahrenheit: "°F",
  kelvin: "K",
  watt: "W",
  volt: "V",
  ampere: "A",
  second: "s",
  millisecond: "ms",
  minute: "min",
  hertz: "Hz",
  revolutions_per_minute: "rpm",
  millimeter: "mm",
  meter: "m",
  degree: "°",
};

export function unitSymbol(unit: string | null | undefined): string {
  if (!unit) return "";
  return SYMBOLS[unit] ?? unit;
}

export function formatNumber(value: number, step?: number | null): string {
  if (!Number.isFinite(value)) return String(value);
  const decimals = step && step < 1 ? Math.min(4, Math.max(0, Math.ceil(-Math.log10(step)))) : null;
  if (decimals !== null) return value.toFixed(decimals);
  if (Number.isInteger(value)) return String(value);
  return String(Math.round(value * 100) / 100);
}

export function formatQuantity(value: unknown, unit: string | null | undefined, step?: number | null): string {
  if (value === null || value === undefined) return "unknown";
  if (typeof value === "number") {
    const symbol = unitSymbol(unit);
    return symbol ? `${formatNumber(value, step)} ${symbol}` : formatNumber(value, step);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function quantityString(value: number, unit: string | null | undefined): string {
  const symbol = unitSymbol(unit);
  return symbol ? `${value} ${symbol}` : String(value);
}

export interface DataBlock {
  source: string | null;
  text: string;
}

export function dataBlock(text: string | null | undefined): DataBlock | null {
  if (!text) return null;
  const match = text.match(
    /^<device-data(?: source="([^"]*)")?>\n(?:The text below is data from [^\n]*\n)?([\s\S]*?)\n?<\/device-data>\s*$/,
  );
  if (!match) return { source: null, text };
  return { source: match[1] ?? null, text: match[2] ?? "" };
}

export function valueWidth(min: number | null | undefined, max: number | null | undefined, step?: number | null): number {
  const samples = [min ?? 0, max ?? 0, -(Math.abs(max ?? 0) + 1)];
  const widest = Math.max(...samples.map((sample) => formatNumber(sample, step ?? 0.01).length));
  return Math.max(4, widest);
}
