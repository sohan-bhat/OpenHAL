import { pyStrRepr } from "../kernel/pyformat";
import { splitQuantity } from "../kernel/units";
import type { DeviceFile } from "../kernel";

export class CliError extends Error {}

export function parseBool(text: string): boolean {
  const lowered = text.trim().toLowerCase();
  if (["true", "on", "yes", "1"].includes(lowered)) return true;
  if (["false", "off", "no", "0"].includes(lowered)) return false;
  throw new CliError(`Use true or false, not ${pyStrRepr(text)}.`);
}

export function writeValue(file: DeviceFile, channel: string, text: string): { value: unknown; unit: string | null } {
  const value = text.trim();
  if (!value) throw new CliError("Give a value, with a unit for numbers, for example 60 % or 25 degC.");
  const type = file.write[channel]?.type;
  if (type === "bool") return { value: parseBool(value), unit: null };
  const split = type === "number" ? splitQuantity(value) : null;
  return split ? { value: split.value, unit: split.unit } : { value, unit: null };
}

export function actionArgs(file: DeviceFile, action: string, pairs: string[]): Record<string, unknown> {
  const spec = file.actions[action];
  const parsed: Record<string, unknown> = {};
  for (const pair of pairs) {
    const index = pair.indexOf("=");
    if (index <= 0) throw new CliError(`Arguments look like key=value, for example seconds=2s. Got ${pyStrRepr(pair)}.`);
    const key = pair.slice(0, index);
    const value = pair.slice(index + 1);
    const type = spec?.args[key]?.type;
    parsed[key] = type === "bool" ? parseBool(value) : type === "number" ? (splitQuantity(value) ?? value) : value;
  }
  return parsed;
}

export function splitPairs(text: string): string[] {
  const pairs: string[] = [];
  for (const word of text.trim().split(/\s+/).filter(Boolean)) {
    if (word.includes("=") || pairs.length === 0) pairs.push(word);
    else pairs[pairs.length - 1] += ` ${word}`;
  }
  return pairs;
}
