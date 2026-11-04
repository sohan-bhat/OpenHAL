import {AbsoluteFill} from 'remotion';
import {Arm3D} from './Arm3D';
import {edit} from './Demo';
import {DeskSceneSpec, poseOf} from './edit';
import {Wordmark} from './EndCard';
import {COLOR, MONO} from './theme';

export const DemoThumbnail: React.FC<{scene: string; frame: number}> = ({scene, frame}) => {
  const spec = edit.scenes.find((s): s is DeskSceneSpec => s.id === scene && s.kind === 'desk');
  if (!spec) {
    throw new Error(`The edit has no desk scene ${scene}`);
  }
  const panel = spec.panel;
  const value = panel.value === 'speed' ? spec.speeds[frame] : panel.value;
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <div style={{position: 'absolute', left: 460, top: 0, width: 820, height: 720}}>
        <Arm3D
          pose={poseOf(spec.poses[frame])}
          camera={{position: [0.36, -0.62, 0.4], target: [0.105, -0.05, 0.11], fov: 30}}
          width={820}
          height={720}
        />
      </div>
      <div style={{position: 'absolute', left: 72, top: 64}}>
        <Wordmark size={64} />
      </div>
      <div style={{position: 'absolute', left: 72, top: 246, color: COLOR.text}}>
        <div style={{fontFamily: MONO, fontSize: 26, color: COLOR.text2}}>{panel.label}</div>
        <div style={{display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 4}}>
          <span style={{fontFamily: MONO, fontSize: 150, letterSpacing: '-0.04em', lineHeight: 1}}>{Math.round(value)}</span>
          <span style={{fontFamily: MONO, fontSize: 40, color: COLOR.text2}}>{panel.unit}</span>
        </div>
        <div style={{fontFamily: MONO, fontWeight: 700, fontSize: 54, color: COLOR.blocked, marginTop: 34}}>{panel.verdict?.text}</div>
        <div style={{fontFamily: MONO, fontSize: 26, color: COLOR.text2, marginTop: 18}}>{panel.limitLabel}</div>
      </div>
    </AbsoluteFill>
  );
};
