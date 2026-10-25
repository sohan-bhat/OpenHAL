// How `openhal write` and `openhal action` turn typed words into a command (openhal/cli), so the
// playground's request line behaves like the real command line.

import { pyStrRepr } from "../kernel/pyformat";
import type { DeviceFile } from "../kernel";

export class CliError extends Error {}

export function parseBool(text: string): boolean {
  const lowered = text.trim().toLowerCase();
  if (["true", "on", "yes", "1"].includes(lowered)) return true;
  if (["false", "off", "no", "0"].includes(lowered)) return false;
  throw new CliError(`Expected true or false, got ${pyStrRepr(text)}.`);
}

/** `_write_value` in openhal/cli/control_cmd.py. */
export function writeValue(file: DeviceFile, channel: string, text: string): unknown {
  const value = text.trim();
  if (!value) throw new CliError("Give a value, with a unit for numbers, for example 60 % or 25 degC.");
  if (file.write[channel]?.type === "bool") return parseBool(value);
  return value;
}

/** `parse_pairs` in openhal/cli/_common.py. Bool arguments become true or false, the rest stays text. */
export function actionArgs(file: DeviceFile, action: string, pairs: string[]): Record<string, unknown> {
  const spec = file.actions[action];
  const parsed: Record<string, unknown> = {};
  for (const pair of pairs) {
    const index = pair.indexOf("=");
    if (index <= 0) throw new CliError(`Arguments look like key=value, for example seconds=2s. Got ${pyStrRepr(pair)}.`);
    const key = pair.slice(0, index);
    const value = pair.slice(index + 1);
    parsed[key] = spec?.args[key]?.type === "bool" ? parseBool(value) : value;
  }
  return parsed;
}

/** Split `seconds=2 s axes=all` into pairs, keeping a unit after a space with its number. */
export function splitPairs(text: string): string[] {
  const pairs: string[] = [];
  for (const word of text.trim().split(/\s+/).filter(Boolean)) {
    if (word.includes("=") || pairs.length === 0) pairs.push(word);
    else pairs[pairs.length - 1] += ` ${word}`;
  }
  return pairs;
}
