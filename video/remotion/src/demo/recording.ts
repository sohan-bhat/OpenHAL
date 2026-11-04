export type Rows = {rate_hz: number; columns: string[]; rows: number[][]};

export type Message = {
  t: number;
  source: string;
  via: string;
  kind: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  is_error?: boolean;
  error?: unknown;
  event?: Record<string, unknown>;
  method?: string;
  path?: string;
  status?: number;
};

export type Beat = {
  name: string;
  t_start: number;
  t_end: number;
  frames: Rows;
  messages: Message[];
};

export const JOINT_NAMES = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll'] as const;
export const SPEED_JOINTS = ['shoulder_pan', 'shoulder_lift', 'elbow_flex'] as const;

export type Vec3 = [number, number, number];
export type Quat = [number, number, number, number];

export type ArmPose = {
  joints: Record<string, number>;
  jaw: number;
  cube: {position: Vec3; quaternion: Quat};
};

const PHYSICS_STEP = 1 / 240;

export class Track {
  readonly rate: number;
  readonly t0: number;
  readonly t1: number;
  private readonly index: Record<string, number>;
  private readonly rows: number[][];

  constructor(beats: Beat[]) {
    const first = beats[0].frames;
    this.rate = first.rate_hz;
    this.index = Object.fromEntries(first.columns.map((name, i) => [name, i]));
    this.rows = beats.flatMap((beat) => beat.frames.rows).sort((a, b) => a[0] - b[0]);
    this.t0 = this.rows[0][0];
    this.t1 = this.rows[this.rows.length - 1][0];
  }

  private find(t: number): [number[], number[], number] {
    const rows = this.rows;
    if (t <= rows[0][0]) {
      return [rows[0], rows[0], 0];
    }
    if (t >= rows[rows.length - 1][0]) {
      const last = rows[rows.length - 1];
      return [last, last, 0];
    }
    let lo = 0;
    let hi = rows.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (rows[mid][0] <= t) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
    const a = rows[lo];
    const b = rows[hi];
    const span = b[0] - a[0];
    return [a, b, span > 0 ? (t - a[0]) / span : 0];
  }

  value(name: string, t: number): number {
    const i = this.index[name];
    if (i === undefined) {
      throw new Error(`The recording has no column ${name}`);
    }
    const [a, b, k] = this.find(t);
    return a[i] + (b[i] - a[i]) * k;
  }

  pose(t: number): ArmPose {
    const joints: Record<string, number> = {};
    for (const name of JOINT_NAMES) {
      joints[name] = this.value(name, t);
    }
    const tc = t + PHYSICS_STEP;
    const q: Quat = [this.value('cube_qw', tc), this.value('cube_qx', tc), this.value('cube_qy', tc), this.value('cube_qz', tc)];
    const norm = Math.hypot(...q) || 1;
    return {
      joints,
      jaw: this.value('gripper_jaw', t),
      cube: {
        position: [this.value('cube_x', tc), this.value('cube_y', tc), this.value('cube_z', tc)],
        quaternion: q.map((v) => v / norm) as Quat,
      },
    };
  }

  jointSpeed(name: string, t: number, window = 2 / 120): number {
    return Math.abs(this.value(name, t + window) - this.value(name, t - window)) / (2 * window);
  }

  fastestJoint(t: number, joints: readonly string[] = SPEED_JOINTS): {name: string; speed: number} {
    let best = {name: joints[0], speed: 0};
    for (const name of joints) {
      const speed = this.jointSpeed(name, t);
      if (speed > best.speed) {
        best = {name, speed};
      }
    }
    return best;
  }
}

export type Clip = {track: Track; start: number; speed: number; fps: number};

export const clipTime = (clip: Clip, frame: number) => clip.start + (frame / clip.fps) * clip.speed;

export const frameOf = (clip: Clip, t: number) => Math.round(((t - clip.start) / clip.speed) * clip.fps);
