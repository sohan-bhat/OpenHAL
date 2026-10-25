// Constants the hero shares between its build-time render and its browser script.
// Nothing here may import the YAML parser, so the browser bundle stays small.

import type { Decision } from "./kernel";

export const HERO_FILE_PATH = "spec/examples/desk-fan-confirmed.hal.yaml";
export const HERO_DEVICE = "desk-fan";
export const HERO_CHANNEL = "fan_speed";
export const HERO_FIRST_REQUEST = "150 %";
export const HERO_PRESETS = ["40 %", "150 %", "-10 %", "95 degF"];
export const HERO_START_TEMPERATURE = 31;
/** The track shows a little beyond the limits, so attempts past the line have somewhere to land. */
export const TRACK_MIN = -20;
export const TRACK_MAX = 160;
export const TRACK_TICKS = [0, 50, 100, 150];

export function trackPercent(value: number): number {
  const clamped = Math.min(TRACK_MAX, Math.max(TRACK_MIN, value));
  return ((clamped - TRACK_MIN) / (TRACK_MAX - TRACK_MIN)) * 100;
}

/** The line `openhal write` prints for a decision (openhal/cli/_common.py, print_decision). */
export function cliLine(decision: Pick<Decision, "status" | "code" | "message">): string {
  const code = decision.code && decision.status !== "done" ? ` ${decision.code}` : "";
  return `${decision.status}${code}  ${decision.message}`;
}
