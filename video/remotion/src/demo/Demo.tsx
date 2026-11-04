import {Audio} from '@remotion/media';
import {AbsoluteFill, Sequence, staticFile} from 'remotion';
import editData from './edit.json';
import {Edit} from './edit';
import {SceneView} from './Scenes';
import {COLOR} from './theme';

export const edit = editData as unknown as Edit;

export type DemoProps = {sound: boolean};

export const OpenHALDemo: React.FC<DemoProps> = ({sound}) => (
  <AbsoluteFill style={{background: COLOR.bg}}>
    {edit.scenes.map((scene) => (
      <Sequence key={scene.id} name={scene.id} from={scene.from} durationInFrames={scene.frames} premountFor={45}>
        <SceneView scene={scene} header={edit.header} />
      </Sequence>
    ))}
    {sound ? <Audio src={staticFile('demo/mix.wav')} /> : null}
  </AbsoluteFill>
);

export const DemoScene: React.FC<{id: string}> = ({id}) => {
  const scene = edit.scenes.find((s) => s.id === id);
  if (!scene) {
    throw new Error(`The edit has no scene ${id}`);
  }
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <SceneView scene={scene} header={edit.header} />
    </AbsoluteFill>
  );
};
