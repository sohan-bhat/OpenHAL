import {useThree} from '@react-three/fiber';
import {useLayoutEffect, useRef, useState} from 'react';
import {staticFile, useDelayRender} from 'remotion';
import {BufferGeometry, LoadingManager, Material, Mesh} from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import URDFLoader, {URDFRobot} from 'urdf-loader';

export const JOINTS = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'] as const;
export const TOOL_LINK = 'gripper_frame_link';

const URDF_DIR = 'so101/';
const URDF_FILE = 'so101_new_calib.urdf';

export type ArmMaterials = {printed: Material; servo: Material};

const firstGeometry = (scene: {traverse: (fn: (child: unknown) => void) => void}, name: string) => {
  let found: BufferGeometry | null = null;
  scene.traverse((child) => {
    if (!found && child instanceof Mesh) {
      found = child.geometry as BufferGeometry;
    }
  });
  if (!found) {
    throw new Error(`No mesh in ${name}`);
  }
  return found as BufferGeometry;
};

export const useSo101 = (materials: ArmMaterials): URDFRobot | null => {
  const [robot, setRobot] = useState<URDFRobot | null>(null);
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const advance = useThree((state) => state.advance);
  const hold = useRef<number | null>(null);

  useLayoutEffect(() => {
    const handle = delayRender('Loading the SO-101 model');
    hold.current = handle;
    const manager = new LoadingManager();
    const loader = new URDFLoader(manager);
    const gltf = new GLTFLoader(manager);
    const geometries = new Map<string, Promise<BufferGeometry>>();
    let parsed: URDFRobot | null = null;
    let expected = Infinity;
    let loaded = 0;
    let cancelled = false;

    const finish = () => {
      if (!cancelled && parsed && loaded >= expected) {
        setRobot(parsed);
      }
    };

    const geometryFor = (path: string) => {
      let geometry = geometries.get(path);
      if (!geometry) {
        const glb = path.replace(/assets\/([^/]+)\.stl$/, 'glb/$1.glb');
        geometry = gltf.loadAsync(glb).then((result) => firstGeometry(result.scene, glb));
        geometries.set(path, geometry);
      }
      return geometry;
    };

    loader.loadMeshCb = (path, _manager, urdfMaterial, done) => {
      geometryFor(path)
        .then((geometry) => {
          const material = urdfMaterial?.name === 'sts3215' ? materials.servo : materials.printed;
          const mesh = new Mesh(geometry, material);
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          mesh.userData.part = path.split('/').pop()?.replace('.stl', '');
          done(mesh);
          loaded++;
          finish();
        })
        .catch((err: Error) => cancelRender(err));
    };

    fetch(staticFile(URDF_DIR + URDF_FILE))
      .then((response) => response.text())
      .then((xml) => {
        loader.workingPath = staticFile(URDF_DIR);
        expected = new DOMParser().parseFromString(xml, 'text/xml').querySelectorAll('visual mesh').length;
        parsed = loader.parse(xml);
        finish();
      })
      .catch((err: Error) => cancelRender(err));

    return () => {
      cancelled = true;
      if (hold.current === handle) {
        hold.current = null;
        continueRender(handle);
      }
    };
  }, [materials, delayRender, continueRender, cancelRender]);

  useLayoutEffect(() => {
    if (robot && hold.current !== null) {
      advance(performance.now());
      continueRender(hold.current);
      hold.current = null;
    }
  }, [robot, advance, continueRender]);

  return robot;
};

export const poseRobot = (robot: URDFRobot, values: Record<string, number>) => {
  for (const [name, value] of Object.entries(values)) {
    robot.setJointValue(name, value);
  }
};
