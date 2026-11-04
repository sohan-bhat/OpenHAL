import {AbsoluteFill} from 'remotion';
import {Arm3D, CameraPose} from './Arm3D';
import {ArmPose, Vec3} from './recording';
import {COLOR, EASE, clamp01} from './theme';

export const VIEWPORT = {left: 484, top: 92, width: 716, height: 536};

export type CameraMove = {from: CameraPose; to: CameraPose; frames: number};

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const mix3 = (a: Vec3, b: Vec3, t: number): Vec3 => [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];

export const cameraAt = (move: CameraMove, frame: number): CameraPose => {
  const t = EASE.inOut(clamp01(frame / Math.max(1, move.frames)));
  return {position: mix3(move.from.position, move.to.position, t), target: mix3(move.from.target, move.to.target, t), fov: mix(move.from.fov, move.to.fov, t)};
};

export const DESK_CAMERA: CameraMove = {
  from: {position: [0.36, -0.74, 0.46], target: [0.115, -0.06, 0.085], fov: 30},
  to: {position: [0.33, -0.68, 0.42], target: [0.115, -0.06, 0.085], fov: 30},
  frames: 240,
};

export const DeskScene: React.FC<{pose: ArmPose; camera: CameraPose; panel: React.ReactNode; aside?: React.ReactNode}> = ({pose, camera, panel, aside}) => (
  <AbsoluteFill style={{background: COLOR.bg}}>
    {panel}
    <div
      style={{
        position: 'absolute',
        left: VIEWPORT.left,
        top: VIEWPORT.top,
        width: VIEWPORT.width,
        height: VIEWPORT.height,
        overflow: 'hidden',
        borderRadius: 6,
        boxShadow: `0 0 0 1px ${COLOR.border}`,
      }}
    >
      <Arm3D pose={pose} camera={camera} width={VIEWPORT.width} height={VIEWPORT.height} />
    </div>
    {aside}
  </AbsoluteFill>
);
