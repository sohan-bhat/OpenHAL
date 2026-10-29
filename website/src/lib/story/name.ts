/**
 * The words OpenHAL's last three letters stand for, Open Hardware Abstraction Layer. The hero sets
 * each label under its own letter, written with its square brackets, the owner's labels of
 * 2026-10-26.
 */
export const SPELLED = [
  { letter: "H", label: "[hardware]" },
  { letter: "A", label: "[abstraction]" },
  { letter: "L", label: "[layer]" },
] as const;

/** The one sentence under the tagline, the owner's words of 2026-10-29. */
export const LEDE = "Agents send requests to the OpenHAL hub, which checks each one against limits you set before anything reaches the device.";
