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

export interface Quantity {
  value: number;
  unit: string;
}

export function isQuantity(value: unknown): value is Quantity {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.value === "number" && typeof record.unit === "string" && Object.keys(record).length === 2;
}

export function quantity(value: number, unit: string | null | undefined): Quantity | number {
  return unit ? { value, unit } : value;
}

export function formatValue(value: unknown): string {
  if (isQuantity(value)) return formatQuantity(value.value, value.unit);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key} ${formatValue(item)}`)
      .join(", ");
  }
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  return formatQuantity(value, null);
}

export function formatQuantity(value: unknown, unit: string | null | undefined, step?: number | null): string {
  if (value === null || value === undefined) return "unknown";
  if (isQuantity(value)) return formatQuantity(value.value, value.unit, step);
  if (typeof value === "object") return formatValue(value);
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

export function formatDateTime(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "";
  const date = new Date(epochSeconds * 1000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
