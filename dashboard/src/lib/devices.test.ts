import { describe, expect, it } from "vitest";
import { reviewable } from "./devices";
import type { DeviceView, Principal } from "./types";

const person: Principal = { kind: "human", name: "owner", scope: "control_medium" };
const agent: Principal = { kind: "agent", name: "claude", scope: "control_medium" };

function lamp(changes: Partial<DeviceView> = {}): DeviceView {
  return {
    writable: false,
    path: "/home/pi/.openhal/devices/bench-lamp.hal.yaml",
    write: { brightness: {} },
    actions: {},
    ...changes,
  } as unknown as DeviceView;
}

describe("Review limits", () => {
  it("shows for a person on a read-only device with a file and something to change", () => {
    expect(reviewable(lamp(), person)).toBe(true);
  });

  it("never shows for an agent's session or before whoami returns the principal", () => {
    expect(reviewable(lamp(), agent)).toBe(false);
    expect(reviewable(lamp(), null)).toBe(false);
  });

  it("stays off for a writable device, a device with no file and a device that only reads", () => {
    expect(reviewable(lamp({ writable: true }), person)).toBe(false);
    expect(reviewable(lamp({ path: null }), person)).toBe(false);
    expect(reviewable(lamp({ write: {} }), person)).toBe(false);
  });
});
