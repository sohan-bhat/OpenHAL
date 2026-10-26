/**
 * The landing story as one shot list, in vh of scroll. A shot glides in from the one before, then
 * dwells while its pieces change. The scene places every cue on this list and the camera frames
 * each shot's targets, so the two can't drift apart. Scrolling back plays it in reverse.
 */

export type ShotId = "wide" | "watch" | "look" | "warm" | "heat" | "hot" | "reply" | "loose" | "pause" | "cancel" | "wake" | "end";

export type Station = "client" | "hub" | "kernel" | "driver" | "printer" | "camera";

export interface Shot {
  id: ShotId;
  target: Station[] | "scene";
  column?: Station[] | "scene";
  glide: number;
  dwell: number;
  pad: number;
  max?: number;
  min?: number;
  top?: boolean;
}

export const CAMERA = "(prefers-reduced-motion: no-preference) and (min-height: 500px)";

export const SHOTS: readonly Shot[] = [
  { id: "wide", target: "scene", glide: 0, dwell: 14, pad: 24 },
  { id: "watch", target: ["client"], glide: 22, dwell: 22, pad: 16, max: 1.5, min: 1 },
  { id: "look", target: ["camera"], glide: 30, dwell: 24, pad: 16, max: 1.6, min: 1 },
  { id: "warm", target: ["client", "hub", "kernel"], glide: 30, dwell: 36, pad: 16, max: 1.1, min: 0.8 },
  { id: "heat", target: ["kernel", "driver", "printer"], glide: 22, dwell: 30, pad: 16, max: 1.1, min: 0.8 },
  { id: "hot", target: ["client", "hub", "kernel"], glide: 26, dwell: 34, pad: 16, max: 1.1, min: 0.8 },
  { id: "reply", target: ["client"], glide: 18, dwell: 18, pad: 16, max: 1.5, min: 1 },
  { id: "loose", target: ["camera"], glide: 30, dwell: 30, pad: 16, max: 1.6, min: 1 },
  { id: "pause", target: ["kernel", "driver", "printer"], glide: 24, dwell: 36, pad: 16, max: 1.1, min: 0.8 },
  { id: "cancel", target: ["client", "hub", "kernel"], glide: 26, dwell: 36, pad: 16, max: 1.1, min: 0.8 },
  { id: "wake", target: ["hub", "kernel", "driver", "printer", "camera"], column: ["hub"], glide: 26, dwell: 28, pad: 16, max: 1, min: 0.6 },
  { id: "end", target: "scene", glide: 22, dwell: 16, pad: 24 },
];

export interface Placed extends Shot {
  glideFrom: number;
  dwellFrom: number;
  end: number;
}

export const PLACED: readonly Placed[] = (() => {
  let t = 0;
  return SHOTS.map((s) => {
    const glideFrom = t;
    const dwellFrom = (t += s.glide);
    return { ...s, glideFrom, dwellFrom, end: (t += s.dwell) };
  });
})();

export const TOTAL = PLACED[PLACED.length - 1].end;

export function shot(id: ShotId): Placed {
  const found = PLACED.find((s) => s.id === id);
  if (!found) throw new Error(`No shot ${id}`);
  return found;
}

/** A point in the story, `offset` into the shot's dwell, or back into its glide when negative. */
export const at = (id: ShotId, offset = 0): number => shot(id).dwellFrom + offset;

/** A point `offset` into the shot's glide. */
export const from = (id: ShotId, offset = 0): number => shot(id).glideFrom + offset;

export const NEVER = 100000;
export const ALWAYS = -NEVER;

const round = (n: number) => Math.round(n * 100) / 100;

/** A piece that arrives at `at` and leaves at `out`, each over `fade`, as the custom properties story.css reads. */
export function cue(arrive: number, out = NEVER, fade = 2): string {
  return `--at: ${round(arrive)}; --out: ${round(out)}; --f: ${fade}`;
}

/** A wire fill that runs from `at` over `run`, then fades at `out`. */
export function run(arrive: number, length: number, out = NEVER): string {
  return `--at: ${round(arrive)}; --d: ${length}; --out: ${round(out)}; --f: 2`;
}
