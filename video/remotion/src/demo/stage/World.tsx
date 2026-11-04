import {Environment, Line, RoundedBox} from '@react-three/drei';
import {createPortal, useThree} from '@react-three/fiber';
import {ThreeCanvas} from '@remotion/three';
import {useMemo} from 'react';
import {staticFile, usePixelDensity} from 'remotion';
import {
  ACESFilmicToneMapping,
  BufferGeometry,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  PerspectiveCamera,
  Quaternion,
  Vector3,
} from 'three';
import {URDFRobot} from 'urdf-loader';
import {poseRobot, useSo101} from '../../so101';
import {Bin, CameraPose, DEG, Desk, Lights, SET, useMaterials, yUp} from '../Arm3D';
import {ArmPose, Vec3} from '../recording';
import {COLOR} from '../theme';

export const LAYER = {y: -0.31, from: -0.6, to: 0.8, sheet: 0.085};
export const PULSE_PATH: Vec3[] = [
  [0.12, -0.44, 0.002],
  [0.12, LAYER.y, 0.002],
  [0.05, -0.12, 0.002],
  [0.02, -0.055, 0.002],
];
const PULSE_LENGTH = 0.07;

export type PulseState = {head: number; color: string; visible: number};
export type WedgeState = {show: number; sweep: number; ghost: number[] | null; ghostShow: number; hit: number};

const pathLengths = (points: Vec3[]) => {
  const out = [0];
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    out.push(out[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]));
  }
  return out;
};

const LENGTHS = pathLengths(PULSE_PATH);
export const PATH_TOTAL = LENGTHS[LENGTHS.length - 1];
export const LAYER_DISTANCE = LENGTHS[1];

export const pointAt = (d: number): Vec3 => {
  const x = Math.min(PATH_TOTAL, Math.max(0, d));
  for (let i = 1; i < PULSE_PATH.length; i++) {
    if (x <= LENGTHS[i]) {
      const [a, b] = [PULSE_PATH[i - 1], PULSE_PATH[i]];
      const t = (x - LENGTHS[i - 1]) / (LENGTHS[i] - LENGTHS[i - 1] || 1);
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    }
  }
  return PULSE_PATH[PULSE_PATH.length - 1];
};

const segment = (from: number, to: number): Vec3[] => {
  const points: Vec3[] = [pointAt(from)];
  for (let i = 1; i < PULSE_PATH.length - 1; i++) {
    if (LENGTHS[i] > from && LENGTHS[i] < to) {
      points.push(PULSE_PATH[i]);
    }
  }
  points.push(pointAt(to));
  return points;
};

const Layer: React.FC<{flat: number}> = ({flat}) => {
  const color = new Color(COLOR.accent).lerp(new Color(COLOR.border), flat);
  const height = LAYER.sheet * (1 - flat);
  const width = LAYER.to - LAYER.from;
  return (
    <>
      <Line points={[yUp([LAYER.from, LAYER.y, 0.0015]), yUp([LAYER.to, LAYER.y, 0.0015])]} color={color} lineWidth={2.2} />
      {height > 0.001 ? (
        <mesh position={yUp([(LAYER.from + LAYER.to) / 2, LAYER.y, height / 2])}>
          <planeGeometry args={[width, height]} />
          <meshBasicMaterial color={COLOR.accent} transparent opacity={0.07 * (1 - flat)} side={DoubleSide} depthWrite={false} />
        </mesh>
      ) : null}
    </>
  );
};

const Pulse: React.FC<{state: PulseState}> = ({state}) => {
  if (state.visible <= 0) {
    return null;
  }
  const head = state.head;
  const tail = Math.max(0, head - PULSE_LENGTH);
  return (
    <>
      <Line points={PULSE_PATH.map(yUp)} color={state.color} lineWidth={1.2} transparent opacity={0.28 * state.visible} />
      {head > tail + 0.002 ? <Line points={segment(tail, head).map(yUp)} color={state.color} lineWidth={4.5} transparent opacity={state.visible} /> : null}
    </>
  );
};

const ghostMaterials = () => ({
  printed: new MeshBasicMaterial({color: new Color(COLOR.blocked), transparent: true, opacity: 0.08, depthWrite: false}),
  servo: new MeshBasicMaterial({color: new Color(COLOR.blocked), transparent: true, opacity: 0.08, depthWrite: false}),
});

const setPose = (robot: URDFRobot, row: number[]) => {
  const names = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll'];
  const values: Record<string, number> = {gripper: row[5] * DEG};
  names.forEach((name, i) => {
    values[name] = row[i] * DEG;
  });
  poseRobot(robot, values);
  robot.updateMatrixWorld(true);
};

const wedgeGeometry = (robot: URDFRobot, sweep: number) => {
  const joint = robot.joints.shoulder_pan;
  joint.updateMatrixWorld(true);
  const tip = new Vector3();
  robot.links.gripper_frame_link?.getWorldPosition(tip);
  const local = joint.worldToLocal(tip.clone());
  const axis = joint.axis.clone().normalize();
  const radial = local.clone().sub(axis.clone().multiplyScalar(local.dot(axis)));
  const e1 = radial.normalize();
  const e2 = axis.clone().cross(e1);
  const radius = 0.16;
  const steps = 48;
  const positions: number[] = [];
  for (let i = 0; i < steps; i++) {
    const a = (sweep * i) / steps;
    const b = (sweep * (i + 1)) / steps;
    const pa = e1.clone().multiplyScalar(Math.cos(a) * radius).add(e2.clone().multiplyScalar(Math.sin(a) * radius));
    const pb = e1.clone().multiplyScalar(Math.cos(b) * radius).add(e2.clone().multiplyScalar(Math.sin(b) * radius));
    positions.push(0, 0, 0, pa.x, pa.y, pa.z, pb.x, pb.y, pb.z);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  return {geometry, edge: e1.clone().multiplyScalar(Math.cos(sweep) * radius).add(e2.clone().multiplyScalar(Math.sin(sweep) * radius))};
};

const Wedge: React.FC<{robot: URDFRobot; state: WedgeState}> = ({robot, state}) => {
  const joint = robot.joints.shoulder_pan;
  const {geometry, edge} = useMemo(() => wedgeGeometry(robot, state.sweep), [robot, state.sweep]);
  const material = useMemo(() => new MeshBasicMaterial({color: new Color(COLOR.accent), transparent: true, depthWrite: false, depthTest: false, side: DoubleSide}), []);
  material.opacity = 0.42 * state.show;
  if (state.show <= 0) {
    return null;
  }
  return createPortal(
    <>
      <mesh geometry={geometry} material={material} renderOrder={2} />
      <Line points={[[0, 0, 0], [edge.x, edge.y, edge.z]]} color={state.hit > 0 ? COLOR.blocked : COLOR.accent} lineWidth={3} transparent opacity={state.show} depthTest={false} renderOrder={3} />
    </>,
    joint,
  );
};

const GHOST_CHAIN = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll'];

const Ghost: React.FC<{row: number[]; show: number}> = ({row, show}) => {
  const materials = useMemo(ghostMaterials, []);
  const robot = useSo101(materials, 'glb-lite');
  if (!robot || show <= 0) {
    return null;
  }
  setPose(robot, row);
  const points: [number, number, number][] = [];
  const at = new Vector3();
  for (const name of GHOST_CHAIN) {
    robot.joints[name].getWorldPosition(at);
    const local = robot.worldToLocal(at.clone());
    points.push([local.x, local.y, local.z]);
  }
  robot.links.gripper_frame_link?.getWorldPosition(at);
  const tip = robot.worldToLocal(at.clone());
  points.push([tip.x, tip.y, tip.z]);
  return <Line points={points} color={COLOR.blocked} lineWidth={3.2} dashed dashSize={0.012} gapSize={0.008} transparent opacity={show} depthTest={false} renderOrder={4} />;
};

export type WorldProps = {pose: ArmPose; camera: CameraPose; flat: number; pulse: PulseState | null; wedge: WedgeState | null};

const Scene: React.FC<WorldProps> = ({pose, camera, flat, pulse, wedge}) => {
  const materials = useMaterials();
  const robot = useSo101(materials, 'glb-lite');
  const cam = useThree((state) => state.camera) as PerspectiveCamera;
  const size = useThree((state) => state.size);

  cam.position.set(...yUp(camera.position));
  cam.up.set(0, 1, 0);
  cam.fov = camera.fov;
  cam.aspect = size.width / size.height;
  cam.near = 0.01;
  cam.far = 20;
  cam.lookAt(new Vector3(...yUp(camera.target)));
  cam.updateProjectionMatrix();

  if (robot) {
    setPose(robot, [pose.joints.shoulder_pan, pose.joints.shoulder_lift, pose.joints.elbow_flex, pose.joints.wrist_flex, pose.joints.wrist_roll, pose.jaw]);
  }

  const [w, x, y, z] = pose.cube.quaternion;
  const s = SET.cube.size;
  return (
    <>
      <color attach="background" args={[COLOR.bg]} />
      <fog attach="fog" args={[COLOR.bg, 1.3, 2.8]} />
      <Environment files={staticFile('hdri/studio_small_09_2k.hdr')} environmentIntensity={0.35} environmentRotation={[0, 2.1, 0]} />
      <Lights />
      <Desk />
      <Bin material={materials.bin} />
      <Layer flat={flat} />
      {pulse ? <Pulse state={pulse} /> : null}
      <group rotation={[-Math.PI / 2, 0, 0]}>
        {robot ? <primitive object={robot} /> : null}
        {robot && wedge ? <Wedge robot={robot} state={wedge} /> : null}
        {wedge?.ghost ? <Ghost row={wedge.ghost} show={wedge.ghostShow} /> : null}
        <group position={pose.cube.position} quaternion={new Quaternion(x, y, z, w)}>
          <RoundedBox args={[s, s, s]} radius={0.0015} smoothness={3} material={materials.cube as MeshPhysicalMaterial} castShadow receiveShadow />
        </group>
      </group>
    </>
  );
};

export const World: React.FC<WorldProps & {width: number; height: number}> = ({width, height, ...props}) => {
  const density = usePixelDensity();
  return (
    <ThreeCanvas width={width} height={height} shadows dpr={density} gl={{antialias: true, toneMapping: ACESFilmicToneMapping, toneMappingExposure: 1.0, powerPreference: 'high-performance'}}>
      <Scene {...props} />
    </ThreeCanvas>
  );
};

export const projectPoint = (camera: CameraPose, point: Vec3, width: number, height: number): [number, number] => {
  const cam = new PerspectiveCamera(camera.fov, width / height, 0.01, 20);
  cam.position.set(...yUp(camera.position));
  cam.up.set(0, 1, 0);
  cam.lookAt(new Vector3(...yUp(camera.target)));
  cam.updateMatrixWorld(true);
  const v = new Vector3(...yUp(point)).project(cam);
  return [((v.x + 1) / 2) * width, ((1 - v.y) / 2) * height];
};
