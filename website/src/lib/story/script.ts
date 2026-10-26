/**
 * The landing story as one shot list, in vh of scroll. A shot glides in from the one before, then
 * dwells while its pieces change. The scene places every cue on this list and the camera frames
 * each shot's targets, so the two can't drift apart. Scrolling back plays it in reverse.
 */

export type ShotId = "wide" | "ask" | "check" | "reply" | "dry" | "hold" | "refill" | "water" | "soil" | "done" | "end";

export type Station = "client" | "hub" | "kernel" | "driver" | "device";

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
  { id: "wide", target: "scene", glide: 0, dwell: 14, pad: 24, top: true },
  { id: "ask", target: ["client"], glide: 22, dwell: 22, pad: 16, max: 1.5, min: 1 },
  { id: "check", target: ["hub", "kernel"], glide: 30, dwell: 34, pad: 16, max: 1.3, min: 0.95 },
  { id: "reply", target: ["client", "hub", "kernel"], column: ["client"], glide: 24, dwell: 22, pad: 16, max: 1.1, min: 0.95 },
  { id: "dry", target: ["device"], glide: 34, dwell: 20, pad: 16, max: 1.5, min: 1 },
  { id: "hold", target: ["kernel", "driver", "device"], glide: 22, dwell: 34, pad: 16, max: 1.1, min: 0.95 },
  { id: "refill", target: ["device"], glide: 20, dwell: 20, pad: 16, max: 1.5, min: 1 },
  { id: "water", target: ["kernel", "driver", "device"], glide: 20, dwell: 34, pad: 16, max: 1.1, min: 0.95 },
  { id: "soil", target: ["device"], glide: 20, dwell: 34, pad: 16, max: 1.5, min: 1 },
  { id: "done", target: ["client"], glide: 30, dwell: 22, pad: 16, max: 1.5, min: 1 },
  { id: "end", target: "scene", glide: 24, dwell: 18, pad: 24 },
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
