/**
 * The landing story's camera, kept pure so it can be tested. Boxes are in scene px, a frame is the
 * part of the stage a shot may fill, in stage px. A camera is the scene point at the frame's center
 * and the zoom, so it becomes the transform translate(cx - x * z, cy - y * z) scale(z).
 */

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Cam {
  x: number;
  y: number;
  z: number;
}

export interface Fit {
  pad: number;
  max?: number;
  min?: number;
  top?: boolean;
}

export interface Framed {
  glideFrom: number;
  dwellFrom: number;
  end: number;
  from: Cam;
  to: Cam;
}

const REACH = 0.6;
const SCAN_HOLD = 0.15;
export const REFERENCE = { w: 1344, h: 640 };

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
export const smoothstep = (e: number) => e * e * (3 - 2 * e);
export const smootherstep = (e: number) => e * e * e * (e * (e * 6 - 15) + 10);

/** The smallest box that holds every box given. */
export function union(boxes: Box[]): Box {
  const left = Math.min(...boxes.map((box) => box.x));
  const top = Math.min(...boxes.map((box) => box.y));
  const right = Math.max(...boxes.map((box) => box.x + box.w));
  const bottom = Math.max(...boxes.map((box) => box.y + box.h));
  return { x: left, y: top, w: right - left, h: bottom - top };
}

/**
 * Frames a target, centered, as close as `max` allows, with `pad` screen px clear around it. A
 * frame bigger than the reference raises the cap with it. A `top` shot sits its target on the
 * frame's top edge instead. When `min` holds the camera closer than the target fits, the target is
 * scanned from its top to its bottom.
 */
export function framing(target: Box, frame: Box, fit: Fit): { from: Cam; to: Cam } {
  const room = Math.min((frame.w - 2 * fit.pad) / target.w, (frame.h - 2 * fit.pad) / target.h);
  const grow = Math.max(1, Math.min(frame.w / REFERENCE.w, frame.h / REFERENCE.h));
  const z = Math.max(fit.min ?? 0, Math.min((fit.max ?? Infinity) * grow, room));
  const x = target.x + target.w / 2;
  const half = (frame.h / 2 - fit.pad) / z;
  const top = target.y + half;
  const bottom = target.y + target.h - half;
  if (bottom <= top) {
    const held = { x, y: fit.top ? top : target.y + target.h / 2, z };
    return { from: held, to: held };
  }
  return { from: { x, y: top, z }, to: { x, y: bottom, z } };
}

/** The transform that puts a camera's point at the frame's center. */
export function transform(cam: Cam, frame: Box): Cam {
  return {
    x: frame.x + frame.w / 2 - cam.x * cam.z,
    y: frame.y + frame.h / 2 - cam.y * cam.z,
    z: cam.z,
  };
}

/**
 * The camera `e` of the way (already eased) from a to b. Zoom moves evenly in log space, and a move
 * longer than REACH frames pulls back in the middle, so it reads as one shot instead of a whip pan.
 */
export function glide(a: Cam, b: Cam, e: number, frame: Box): Cam {
  const la = Math.log(a.z);
  const lb = Math.log(b.z);
  const near = Math.min(a.z, b.z);
  const travel = Math.max((Math.abs(b.x - a.x) * near) / frame.w, (Math.abs(b.y - a.y) * near) / frame.h);
  const dip = travel > REACH ? Math.min(0, Math.log(near * Math.sqrt(REACH / travel)) - (la + lb) / 2) : 0;
  const z = Math.exp(la + (lb - la) * e + 4 * dip * e * (1 - e));
  const w = (b.z * b.z) / (a.z * a.z + b.z * b.z);
  const px = a.x + (b.x - a.x) * w;
  const py = a.y + (b.y - a.y) * w;
  const sx = (px - a.x) * a.z * (1 - e) + (px - b.x) * b.z * e;
  const sy = (py - a.y) * a.z * (1 - e) + (py - b.y) * b.z * e;
  return { x: px - sx / z, y: py - sy / z, z };
}

/** Where the camera is at story time t. */
export function cameraAt(t: number, shots: readonly Framed[], frame: Box): Cam {
  let last = shots[0].from;
  for (const shot of shots) {
    if (t < shot.dwellFrom) {
      const e = clamp01((t - shot.glideFrom) / (shot.dwellFrom - shot.glideFrom));
      return glide(last, shot.from, smootherstep(e), frame);
    }
    if (t < shot.end) {
      if (shot.from === shot.to) return shot.from;
      const e = clamp01(((t - shot.dwellFrom) / (shot.end - shot.dwellFrom) - SCAN_HOLD) / (1 - 2 * SCAN_HOLD));
      const s = smoothstep(e);
      return { x: shot.from.x, y: shot.from.y + (shot.to.y - shot.from.y) * s, z: shot.from.z };
    }
    last = shot.to;
  }
  return last;
}
