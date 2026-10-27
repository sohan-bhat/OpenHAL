import type { DeviceFile } from "../kernel";

/**
 * What a simulated device reports after an action runs, by driver, the way the hub's own
 * simulators answer. A Klipper printer behind Moonraker reports paused after pause, printing after
 * resume and cancelled after cancel.
 */
const AFTER: Record<string, Record<string, Record<string, string>>> = {
  moonraker: {
    pause: { state: "paused" },
    resume: { state: "printing" },
    cancel: { state: "cancelled" },
  },
};

export function afterAction(file: DeviceFile, action: string): Record<string, string> {
  const changes = AFTER[file.connect.driver]?.[action] ?? {};
  return Object.fromEntries(Object.entries(changes).filter(([channel, value]) => file.read[channel]?.type === "enum" && file.read[channel].values.includes(value)));
}
