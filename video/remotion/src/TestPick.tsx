import {Environment, RoundedBox, SoftShadows} from '@react-three/drei';
import {useFrame, useThree} from '@react-three/fiber';
import {Bloom, DepthOfField, EffectComposer, N8AO, Noise, ToneMapping} from '@react-three/postprocessing';
import {ThreeCanvas} from '@remotion/three';
import {ToneMappingMode} from 'postprocessing';
import {useMemo, useRef} from 'react';
import {AbsoluteFill, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Color, CubicBezierCurve3, Group, Matrix3, Matrix4, Mesh, MeshPhysicalMaterial, Object3D, PerspectiveCamera, TubeGeometry, Vector3} from 'three';
import {RectAreaLightUniformsLib} from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
import cableData from '../../scenes/cables.json';
import look from '../../scenes/look.json';
import shotData from '../../scenes/shots/test_pick.json';
import {Shot, Vec3, cameraAt, jointsAt, verticalFov, zUp} from './shot';
import {TOOL_LINK, poseRobot, useSo101} from './so101';

RectAreaLightUniformsLib.init();

const shot = shotData as unknown as Shot;

export const LIGHTS = {key: 3.2, rim: 5.0, fill: 0.5, wash: 0.5, environment: 0.32};

const physical = (hex: string, roughness: number) =>
  new MeshPhysicalMaterial({color: new Color(hex), roughness, metalness: 0, ior: 1.46});

const useMaterials = () =>
  useMemo(() => {
    const p = look.palette;
    const m = look.materials;
    return {
      printed: physical(p.printed, m.printed.roughness),
      servo: physical(p.servo, m.servo.roughness),
      cable: physical(p.cable, m.cable.roughness),
      desk: physical(p.desk, m.desk.roughness),
      cube: physical(p.cube, m.cube.roughness),
      backdrop: physical(p.backdrop, 0.9),
    };
  }, []);

const yUp = (v: number[]): Vec3 => zUp([v[0], v[1], v[2]]);

type CableEnd = {link: string; point: number[]; tangent: number[]};
type CableSpec = {name: string; radius: number; from: CableEnd; to: CableEnd};
const CABLES = cableData.cables as CableSpec[];

const cableCurve = (spec: CableSpec, links: Record<string, Object3D>) => {
  const ends = [spec.from, spec.to].map((end) => {
    const m = links[end.link].matrixWorld;
    const point = new Vector3(...end.point).applyMatrix4(m);
    const tangent = new Vector3(...end.tangent).applyMatrix3(new Matrix3().setFromMatrix4(m));
    return {point, handle: point.clone().add(tangent)};
  });
  return new CubicBezierCurve3(ends[0].point, ends[0].handle, ends[1].handle, ends[1].point);
};

const Lights: React.FC = () => {
  const key = look.lights.key;
  const rim = look.lights.rim;
  const fill = look.lights.fill;
  const wash = look.lights.wash;
  const keyTarget = useMemo(() => {
    const target = new Object3D();
    target.position.set(...yUp(key.target));
    return target;
  }, [key.target]);
  const aim = (from: number[], to: number[]) => {
    const helper = new Object3D();
    helper.position.set(...yUp(from));
    helper.lookAt(new Vector3(...yUp(to)));
    return helper.rotation.clone();
  };
  return (
    <>
      <primitive object={keyTarget} />
      <spotLight
        position={yUp(key.position)}
        target={keyTarget}
        color={key.color}
        intensity={LIGHTS.key}
        angle={0.62}
        penumbra={1}
        decay={2}
        castShadow
        shadow-mapSize={[4096, 4096]}
        shadow-bias={-0.0001}
        shadow-normalBias={0.0015}
        shadow-camera-near={0.3}
        shadow-camera-far={3}
      />
      <rectAreaLight
        position={yUp(rim.position)}
        rotation={aim(rim.position, rim.target)}
        width={rim.size[0]}
        height={rim.size[1]}
        color={rim.color}
        intensity={LIGHTS.rim}
      />
      <rectAreaLight
        position={yUp(fill.position)}
        rotation={aim(fill.position, fill.target)}
        width={fill.size[0]}
        height={fill.size[1]}
        color={fill.color}
        intensity={LIGHTS.fill}
      />
      <rectAreaLight
        position={yUp(wash.position)}
        rotation={aim(wash.position, wash.target)}
        width={wash.size[0]}
        height={wash.size[1]}
        color={wash.color}
        intensity={LIGHTS.wash}
      />
    </>
  );
};

const Set: React.FC<{materials: ReturnType<typeof useMaterials>}> = ({materials}) => {
  const first = cameraAt(shot, 1);
  const [sx, sy, sz] = look.desk.size;
  const [cx, cy] = look.desk.center;
  const dir = new Vector3(first.target[0] - first.position[0], first.target[1] - first.position[1], 0).normalize();
  const center = new Vector3(...first.target).add(dir.clone().multiplyScalar(look.backdrop.distance));
  const height = look.backdrop.height;
  const yaw = Math.atan2(dir.y, dir.x) + Math.PI / 2;
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <mesh position={[cx, cy, -sz / 2]} material={materials.desk} receiveShadow>
        <boxGeometry args={[sx * 2.2, sy * 2.6, sz]} />
      </mesh>
      <mesh position={[center.x, center.y, height / 2 - 0.05]} rotation={[Math.PI / 2, 0, yaw, 'ZYX']} material={materials.backdrop} receiveShadow>
        <planeGeometry args={[look.backdrop.width, height]} />
      </mesh>
    </group>
  );
};

export type TestPickProps = {post?: boolean; softShadows?: boolean};

const Scene: React.FC<TestPickProps> = ({post = true, softShadows = true}) => {
  const frame = useCurrentFrame() + 1;
  const frameRef = useRef(frame);
  frameRef.current = frame;
  const materials = useMaterials();
  const robot = useSo101(materials);
  const robotRef = useRef(robot);
  robotRef.current = robot;
  const world = useRef<Group>(null);
  const cube = useRef<Object3D>(null);
  const cables = useMemo(
    () =>
      CABLES.map((spec) => {
        const mesh = new Mesh(undefined, materials.cable);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        return {spec, mesh};
      }),
    [materials.cable],
  );
  const focus = useMemo(() => new Vector3(), []);
  const {size} = useThree();

  useFrame(({camera}) => {
    const f = frameRef.current;
    const cam = cameraAt(shot, f);
    const perspective = camera as PerspectiveCamera;
    perspective.position.set(...zUp(cam.position));
    perspective.aspect = size.width / size.height;
    perspective.fov = verticalFov(cam.lensMm, cam.sensorMm, perspective.aspect);
    perspective.near = 0.01;
    perspective.far = 20;
    perspective.up.set(0, 1, 0);
    perspective.lookAt(new Vector3(...zUp(cam.target)));
    perspective.updateProjectionMatrix();
    focus.set(...zUp(cam.focus));
    const robot = robotRef.current;
    if (!robot || !world.current || !cube.current) {
      return;
    }
    world.current.updateMatrixWorld(true);
    const start = new Matrix4()
      .makeRotationZ((shot.cube.yaw_deg * Math.PI) / 180)
      .setPosition(...shot.cube.position);
    const startWorld = world.current.matrixWorld.clone().multiply(start);
    const tool = robot.frames[TOOL_LINK];
    let cubeWorld = startWorld;
    if (shot.cube.attach !== null && f >= shot.cube.attach) {
      poseRobot(robot, jointsAt(shot, shot.cube.attach));
      robot.updateMatrixWorld(true);
      const grip = tool.matrixWorld.clone().invert().multiply(startWorld);
      const held = shot.cube.release === null ? f : Math.min(f, shot.cube.release);
      poseRobot(robot, jointsAt(shot, held));
      robot.updateMatrixWorld(true);
      cubeWorld = tool.matrixWorld.clone().multiply(grip);
    }
    poseRobot(robot, jointsAt(shot, f));
    robot.updateMatrixWorld(true);
    for (const {spec, mesh} of cables) {
      mesh.geometry.dispose();
      mesh.geometry = new TubeGeometry(cableCurve(spec, robot.links), 48, spec.radius, 10, false);
    }
    cube.current.matrixAutoUpdate = false;
    cube.current.matrix.copy(cubeWorld);
    cube.current.matrixWorldNeedsUpdate = true;
  }, -1);

  const s = shot.cube.size;
  return (
    <>
      <color attach="background" args={[look.palette.backdrop]} />
      {softShadows ? <SoftShadows size={22} samples={20} focus={0.35} /> : null}
      <Environment
        files={staticFile(look.hdri.file)}
        environmentIntensity={LIGHTS.environment}
        environmentRotation={[0, (look.hdri.rotation_deg * Math.PI) / 180, 0]}
      />
      <Lights />
      <Set materials={materials} />
      <group ref={world} rotation={[-Math.PI / 2, 0, 0]}>
        {robot ? <primitive object={robot} /> : null}
      </group>
      {cables.map(({spec, mesh}) => (
        <primitive key={spec.name} object={mesh} />
      ))}
      <group ref={cube}>
        <RoundedBox args={[s, s, s]} radius={look.materials.cube.bevel} smoothness={4} material={materials.cube} castShadow receiveShadow />
      </group>
      {post ? (
      <EffectComposer multisampling={4}>
        <N8AO aoRadius={0.035} distanceFalloff={0.6} intensity={2.0} quality="high" />
        <DepthOfField target={focus} worldFocusRange={0.14} bokehScale={7} />
        <Bloom mipmapBlur intensity={0.18} luminanceThreshold={0.88} luminanceSmoothing={0.12} />
        <ToneMapping mode={ToneMappingMode.AGX} />
        <Noise premultiply opacity={0.1} />
      </EffectComposer>
      ) : null}
    </>
  );
};

export const TestPick: React.FC<TestPickProps> = (props) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: look.palette.backdrop}}>
      <ThreeCanvas width={width} height={height} shadows flat dpr={1} gl={{antialias: false, powerPreference: 'high-performance'}}>
        <Scene {...props} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
