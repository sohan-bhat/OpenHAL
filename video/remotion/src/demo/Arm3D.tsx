import {Environment, RoundedBox, useTexture} from '@react-three/drei';
import {useThree} from '@react-three/fiber';
import {ThreeCanvas} from '@remotion/three';
import {useMemo} from 'react';
import {staticFile, usePixelDensity} from 'remotion';
import {
  ACESFilmicToneMapping,
  Color,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  Object3D,
  PerspectiveCamera,
  RepeatWrapping,
  SRGBColorSpace,
  Vector2,
  Vector3,
} from 'three';
import {poseRobot, useSo101} from '../so101';
import {ArmPose, Vec3} from './recording';
import {COLOR} from './theme';

export type CameraPose = {position: Vec3; target: Vec3; fov: number};

const yUp = (v: Vec3): Vec3 => [v[0], v[2], -v[1]];

const DEG = Math.PI / 180;

export const SET = {
  cube: {size: 0.025, color: '#d24a33'},
  bin: {center: [0.12, -0.17] as [number, number], inside: 0.082, wall: 0.004, height: 0.04, color: '#46525e'},
  desk: {size: [1.5, 0.95, 0.03] as Vec3, center: [0.08, 0.02] as [number, number]},
};

const useMaterials = () =>
  useMemo(
    () => ({
      printed: new MeshPhysicalMaterial({color: new Color('#e6e3dc'), roughness: 0.5, metalness: 0, clearcoat: 0.15, clearcoatRoughness: 0.6}),
      servo: new MeshPhysicalMaterial({color: new Color('#161715'), roughness: 0.38, metalness: 0, clearcoat: 0.3, clearcoatRoughness: 0.4}),
      cube: new MeshPhysicalMaterial({color: new Color(SET.cube.color), roughness: 0.55, metalness: 0}),
      bin: new MeshPhysicalMaterial({color: new Color(SET.bin.color), roughness: 0.6, metalness: 0}),
    }),
    [],
  );

const Desk: React.FC = () => {
  const [map, normalMap] = useTexture([staticFile('wood/wood_table_001_diff_2k.jpg'), staticFile('wood/wood_table_001_nor_gl_1k.jpg')]);
  const material = useMemo(() => {
    map.colorSpace = SRGBColorSpace;
    for (const texture of [map, normalMap]) {
      texture.wrapS = RepeatWrapping;
      texture.wrapT = RepeatWrapping;
      texture.rotation = Math.PI / 2;
      texture.center.set(0.5, 0.5);
      texture.anisotropy = 8;
    }
    return new MeshStandardMaterial({map, normalMap, roughness: 0.78, normalScale: new Vector2(0.25, 0.25), envMapIntensity: 0.18, color: new Color('#cfc4bb')});
  }, [map, normalMap]);
  const [sx, sy, sz] = SET.desk.size;
  const [cx, cy] = SET.desk.center;
  return (
    <mesh position={yUp([cx, cy, -sz / 2])} material={material} receiveShadow>
      <boxGeometry args={[sx, sz, sy]} />
    </mesh>
  );
};

const Bin: React.FC<{material: MeshPhysicalMaterial}> = ({material}) => {
  const {inside, wall, height, center} = SET.bin;
  const outer = inside + 2 * wall;
  const half = inside / 2 + wall / 2;
  const walls: {position: Vec3; size: Vec3}[] = [
    {position: [0, half, height / 2], size: [outer, wall, height]},
    {position: [0, -half, height / 2], size: [outer, wall, height]},
    {position: [half, 0, height / 2], size: [wall, inside, height]},
    {position: [-half, 0, height / 2], size: [wall, inside, height]},
    {position: [0, 0, 0.002], size: [inside, inside, 0.004]},
  ];
  return (
    <group position={yUp([center[0], center[1], 0])}>
      {walls.map(({position, size}, i) => (
        <mesh key={i} position={yUp(position)} material={material} castShadow receiveShadow>
          <boxGeometry args={[size[0], size[2], size[1]]} />
        </mesh>
      ))}
    </group>
  );
};

const Lights: React.FC = () => {
  const target = useMemo(() => {
    const object = new Object3D();
    object.position.set(...yUp([0.12, -0.03, 0.04]));
    return object;
  }, []);
  return (
    <>
      <primitive object={target} />
      <spotLight
        position={yUp([-0.35, -0.7, 0.95])}
        target={target}
        color="#fff3e6"
        intensity={7}
        angle={0.5}
        penumbra={0.9}
        decay={1.6}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0002}
        shadow-normalBias={0.002}
        shadow-radius={6}
        shadow-camera-near={0.4}
        shadow-camera-far={2.4}
      />
      <directionalLight position={yUp([0.4, 0.8, 0.5])} color="#e8eeff" intensity={1.6} />
      <hemisphereLight args={['#fff7ee', '#2a1d14', 0.25]} />
    </>
  );
};

const Scene: React.FC<{pose: ArmPose; camera: CameraPose}> = ({pose, camera}) => {
  const materials = useMaterials();
  const robot = useSo101(materials, 'glb-lite');
  const cam = useThree((state) => state.camera) as PerspectiveCamera;
  const size = useThree((state) => state.size);

  cam.position.set(...yUp(camera.position));
  cam.up.set(0, 1, 0);
  cam.fov = camera.fov;
  cam.aspect = size.width / size.height;
  cam.near = 0.02;
  cam.far = 20;
  cam.lookAt(new Vector3(...yUp(camera.target)));
  cam.updateProjectionMatrix();

  if (robot) {
    const values: Record<string, number> = {gripper: pose.jaw * DEG};
    for (const [name, deg] of Object.entries(pose.joints)) {
      values[name] = deg * DEG;
    }
    poseRobot(robot, values);
    robot.updateMatrixWorld(true);
  }

  const [w, x, y, z] = pose.cube.quaternion;
  const s = SET.cube.size;
  return (
    <>
      <color attach="background" args={[COLOR.bg]} />
      <fog attach="fog" args={[COLOR.bg, 1.4, 2.6]} />
      <Environment files={staticFile('hdri/studio_small_09_2k.hdr')} environmentIntensity={0.35} environmentRotation={[0, 2.1, 0]} />
      <Lights />
      <Desk />
      <Bin material={materials.bin} />
      <group rotation={[-Math.PI / 2, 0, 0]}>
        {robot ? <primitive object={robot} /> : null}
        <group position={pose.cube.position} quaternion={[x, y, z, w]}>
          <RoundedBox args={[s, s, s]} radius={0.0015} smoothness={3} material={materials.cube} castShadow receiveShadow />
        </group>
      </group>
    </>
  );
};

export const Arm3D: React.FC<{pose: ArmPose; camera: CameraPose; width: number; height: number}> = ({pose, camera, width, height}) => {
  const density = usePixelDensity();
  return (
    <ThreeCanvas
      width={width}
      height={height}
      shadows
      dpr={density}
      gl={{antialias: true, toneMapping: ACESFilmicToneMapping, toneMappingExposure: 1.0, powerPreference: 'high-performance'}}
    >
      <Scene pose={pose} camera={camera} />
    </ThreeCanvas>
  );
};
