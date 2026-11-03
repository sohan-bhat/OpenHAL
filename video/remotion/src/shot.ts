export type Vec3 = [number, number, number];

export type JointKey = {
  frame: number;
  joints: Record<string, number>;
  ease?: 'linear';
};

export type CameraKey = {
  frame: number;
  position: Vec3;
  target: Vec3;
  focus: Vec3;
  lens_mm: number;
  fstop: number;
};

export type Shot = {
  name: string;
  fps: number;
  frames: number;
  resolution: [number, number];
  arm: {base: Vec3; yaw_deg: number; keys: JointKey[]};
  cube: {size: number; position: Vec3; yaw_deg: number; attach: number | null; release: number | null};
  camera: {sensor_mm: number; keys: CameraKey[]};
};

export type CameraState = {
  position: Vec3;
  target: Vec3;
  focus: Vec3;
  lensMm: number;
  fstop: number;
  sensorMm: number;
};

export const minJerk = (t: number): number => {
  const x = Math.min(Math.max(t, 0), 1);
  return x * x * x * (10 + x * (-15 + 6 * x));
};

const segment = <K extends {frame: number; ease?: 'linear'}>(keys: K[], frame: number): [K, K, number] => {
  if (frame <= keys[0].frame) {
    return [keys[0], keys[0], 0];
  }
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i];
    const b = keys[i + 1];
    if (a.frame <= frame && frame <= b.frame) {
      const span = b.frame - a.frame;
      const t = span ? (frame - a.frame) / span : 1;
      return [a, b, b.ease === 'linear' ? t : minJerk(t)];
    }
  }
  const last = keys[keys.length - 1];
  return [last, last, 0];
};

const mix = (a: number, b: number, t: number) => a + (b - a) * t;

const mix3 = (a: Vec3, b: Vec3, t: number): Vec3 => [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];

export const jointsAt = (shot: Shot, frame: number): Record<string, number> => {
  const [a, b, t] = segment(shot.arm.keys, frame);
  const out: Record<string, number> = {};
  for (const name of Object.keys(a.joints)) {
    out[name] = (mix(a.joints[name], b.joints[name], t) * Math.PI) / 180;
  }
  return out;
};

export const cameraAt = (shot: Shot, frame: number): CameraState => {
  const [a, b, t] = segment(shot.camera.keys, frame);
  return {
    position: mix3(a.position, b.position, t),
    target: mix3(a.target, b.target, t),
    focus: mix3(a.focus, b.focus, t),
    lensMm: mix(a.lens_mm, b.lens_mm, t),
    fstop: mix(a.fstop, b.fstop, t),
    sensorMm: shot.camera.sensor_mm,
  };
};

export const zUp = (v: Vec3): Vec3 => [v[0], v[2], -v[1]];

export const verticalFov = (lensMm: number, sensorMm: number, aspect: number): number => {
  const half = Math.atan(sensorMm / 2 / lensMm);
  return (2 * Math.atan(Math.tan(half) / aspect) * 180) / Math.PI;
};
