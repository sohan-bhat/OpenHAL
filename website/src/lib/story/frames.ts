/**
 * The webcam's two demo frames as SVG paths, on the same 640 by 480 grid, with the same points and
 * in the same drawing order as openhal/demo/frames.py, which draws the JPEGs the simulated webcam
 * serves, and the print as it started, drawn from the first frame's points before the agent reads
 * the webcam. The site draws them as lines that follow the light and dark themes, and shows the
 * part below y 120, where every frame draws. A shape that hides what is behind it is filled with
 * the page's own background. The parts marked seen are what the agent notices in the frame.
 */

type Point = [number, number];

export type Fill = "bg" | "none";

export interface Ink {
  d: string;
  fill: Fill;
  seen: boolean;
}

export interface Frame {
  items: Ink[];
}

const path = (points: Point[], closed = false) => `M${points.map(([x, y]) => `${+x.toFixed(1)} ${+y.toFixed(1)}`).join(" L")}${closed ? " Z" : ""}`;
const shape = (points: Point[], fill: Fill = "none", seen = false): Ink => ({ d: path(points, true), fill, seen });
const line = (points: Point[], seen = false): Ink => ({ d: path(points), fill: "none", seen });

const bed = [
  shape([[150, 250], [490, 250], [590, 420], [50, 420]]),
  shape([[50, 420], [590, 420], [590, 432], [50, 432]]),
  ...[120, 520].map((x) => line([[x, 432], [x, 470]])),
];

const toolhead = ([x, y]: Point) => [
  line([[40, y - 92], [600, y - 92]]),
  line([[40, y - 80], [600, y - 80]]),
  shape([[x - 42, y - 104], [x + 42, y - 104], [x + 42, y - 46], [x - 42, y - 46]], "bg"),
  shape([[x - 16, y - 46], [x + 16, y - 46], [x + 16, y - 16], [x - 16, y - 16]], "bg"),
  shape([[x - 9, y - 16], [x + 9, y - 16], [x, y]], "bg"),
];

function strand(center: Point, radius: number, turns: number, start: number): Point[] {
  const steps = Math.max(8, Math.trunc(turns * 24));
  return Array.from({ length: steps + 1 }, (_, step) => {
    const angle = start + (2 * Math.PI * turns * step) / steps;
    const wobble = 1 + 0.18 * Math.sin(3.1 * angle);
    return [center[0] + radius * wobble * Math.cos(angle), center[1] + 0.45 * radius * Math.sin(angle)] as Point;
  });
}

/**
 * The print as it started, before the agent first reads the webcam. It is the first-layer frame
 * with the corner still flat on the bed, where the frame's own outline of the gap meets the bed.
 */
function printing(): Frame {
  const [frontLeft, frontRight, frontRightLow]: Point[] = [[214, 372], [428, 372], [428, 377]];
  return {
    items: [...bed, shape([frontLeft, frontRight, frontRightLow, [214, 377]]), shape([[232, 332], [400, 332], frontRight, frontLeft]), ...toolhead([262, 326])],
  };
}

function lifting(): Frame {
  const [frontLeft, bend, bendLow, corner, cornerLow]: Point[] = [[214, 372], [340, 372], [340, 377], [438, 324], [438, 331]];
  return {
    items: [
      ...bed,
      shape([frontLeft, bend, bendLow, [214, 377]]),
      shape([bend, corner, cornerLow, bendLow], "none", true),
      shape([[232, 332], [400, 332], corner, bend, frontLeft]),
      shape([bendLow, cornerLow, [428, 377]], "bg", true),
      line([bendLow, [428, 377], cornerLow], true),
      ...toolhead([262, 326]),
    ],
  };
}

function loose(): Frame {
  const nozzle: Point = [262, 250];
  const nest = ([[34, 1.6, 0.4], [26, 1.3, 2.1], [40, 1.1, 4.0], [20, 1.8, 1.0]] as const).map(([radius, turns, start]) => line(strand([262, 348], radius, turns, start), true));
  return {
    items: [
      ...bed,
      shape([[372, 318], [452, 296], [500, 368], [420, 392]], "none", true),
      shape([[420, 392], [500, 368], [500, 382], [420, 406]], "none", true),
      shape([[372, 318], [420, 392], [420, 406], [372, 332]], "none", true),
      line([[395, 307], [444, 380]], true),
      line([[412, 302], [461, 375]], true),
      line([[430, 298], [479, 371]], true),
      ...toolhead(nozzle),
      line([nozzle, [258, 268], [266, 286], [256, 304], [264, 322], [258, 338]], true),
      ...nest,
    ],
  };
}

export const FRAMES = { printing: printing(), lifting: lifting(), loose: loose() };
