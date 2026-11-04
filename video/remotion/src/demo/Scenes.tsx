import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {DeviceCard, StatCard} from './Cards';
import {Cursor} from './Cursor';
import {DataPanel} from './DataPanel';
import {DeskScene, cameraAt} from './DeskScene';
import {DeskSceneSpec, DevicesScene, EndScene, InspectorScene, Scene, StatsScene, TerminalScene, Tone, poseOf} from './edit';
import {EndCard} from './EndCard';
import {ConfirmationsIntro, DevicesSidebar, INSPECTOR, InspectorHeader, InspectorNav, PendingCard, StoppedBanner} from './Inspector';
import {Terminal, TerminalHeader} from './Terminal';
import {COLOR, EASE, SANS, TIME, progress} from './theme';

const TONE: Record<Tone, string> = {ok: COLOR.ok, blocked: COLOR.blocked, pending: COLOR.confirm, text: COLOR.text};

const pressOf = (frame: number, at: number) => {
  const d = frame - at;
  return d >= 0 && d < 8 ? 1 - Math.abs(d - 2) / 6 : 0;
};

const TerminalView: React.FC<{scene: TerminalScene; header: TerminalHeader}> = ({scene, header}) => (
  <Terminal header={header} blocks={scene.blocks} camera={scene.camera} scroll={scene.scroll} />
);

const STRIP = 56;

const DeskView: React.FC<{scene: DeskSceneSpec}> = ({scene}) => {
  const frame = useCurrentFrame();
  const i = Math.min(scene.poses.length - 1, Math.max(0, frame));
  const pose = poseOf(scene.poses[i]);
  const panel = scene.panel;
  const value =
    panel.value === 'speed'
      ? scene.speeds[i]
      : (panel.countFrom ?? 0) + (panel.value - (panel.countFrom ?? 0)) * progress(frame, 8, panel.countFrames ?? TIME.countUp, EASE.out);
  const shot = (scene.shots ?? []).filter((s) => frame >= s.start).pop();
  const camera = shot ? cameraAt(shot.camera, frame - shot.start) : cameraAt(scene.camera, frame);
  const stop = scene.stop;
  const stopped = stop ? frame >= stop.press : false;
  const offset = stop ? STRIP : 0;
  return (
    <DeskScene
      pose={pose}
      camera={camera}
      offset={offset}
      panel={
        <DataPanel
          frame={frame + 18}
          offset={offset}
          title={panel.title}
          subtitle={panel.subtitle}
          label={panel.label}
          value={value}
          unit={panel.unit}
          limit={panel.limit}
          scaleMax={panel.scaleMax}
          limitLabel={panel.limitLabel}
          verdict={panel.verdict ? {text: panel.verdict.text, color: TONE[panel.verdict.tone], at: panel.verdict.at + 18} : null}
        />
      }
      aside={
        stop ? (
          <>
            <InspectorHeader hub={stop.hub} stopped={stopped} pressed={pressOf(frame, stop.press)} />
            {stopped ? <StoppedBanner reason={stop.reason} top={INSPECTOR.headerHeight} opacity={progress(frame, stop.press + 2, 6)} /> : null}
            <Cursor keys={stop.cursor} clicks={[stop.press]} />
          </>
        ) : null
      }
    />
  );
};

const InspectorView: React.FC<{scene: InspectorScene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const zoom = interpolate(frame, [0, scene.frames], [scene.zoom.from, scene.zoom.to], {extrapolateRight: 'clamp', easing: EASE.inOut});
  const last = scene.cursor[scene.cursor.length - 1];
  const hover = frame >= last.at && frame < scene.press;
  const press = pressOf(frame, scene.press);
  return (
    <AbsoluteFill style={{background: COLOR.bg, overflow: 'hidden'}}>
      <AbsoluteFill style={{scale: `${zoom}`, transformOrigin: `${scene.zoom.origin[0]}px ${scene.zoom.origin[1]}px`}}>
        <InspectorHeader hub={scene.hub} stopped={false} />
        <InspectorNav active="Confirmations" pending={1} />
        <DevicesSidebar top={INSPECTOR.headerHeight + INSPECTOR.navHeight} device={scene.device} />
        <ConfirmationsIntro pending={1} />
        <PendingCard request={scene.request} hover={hover} approvePress={press} />
        <Cursor keys={scene.cursor} clicks={[scene.press]} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const StatsView: React.FC<{scene: StatsScene}> = ({scene}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <div style={{position: 'absolute', left: 80, top: 150, display: 'flex', gap: 120}}>
        {scene.stats.map((stat, i) => (
          <StatCard key={stat.label} stat={stat} at={4 + i * TIME.stagger * 2} />
        ))}
      </div>
      <div style={{position: 'absolute', left: 80, bottom: 70, fontFamily: SANS, fontSize: 22, color: COLOR.text2, opacity: progress(frame, 30, 12)}}>{scene.source}</div>
    </AbsoluteFill>
  );
};

const DevicesView: React.FC<{scene: DevicesScene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const head = progress(frame, 0, 12);
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <div style={{position: 'absolute', left: 64, top: 118, fontFamily: SANS, fontWeight: 700, fontSize: 48, letterSpacing: '-0.02em', color: COLOR.text, opacity: head, translate: `0 ${(1 - head) * 10}px`}}>
        {scene.title}
      </div>
      <div style={{position: 'absolute', left: 64, right: 64, top: 236, display: 'flex', gap: 28}}>
        {scene.devices.map((device, i) => (
          <DeviceCard key={device.file} device={device} at={10 + i * TIME.stagger} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

const EndView: React.FC<{scene: EndScene}> = ({scene}) => <EndCard tagline={scene.tagline} command={scene.command} url={scene.url} finePrint={scene.finePrint} />;

export const SceneView: React.FC<{scene: Scene; header: TerminalHeader}> = ({scene, header}) => {
  switch (scene.kind) {
    case 'terminal':
      return <TerminalView scene={scene} header={header} />;
    case 'desk':
      return <DeskView scene={scene} />;
    case 'inspector':
      return <InspectorView scene={scene} />;
    case 'stats':
      return <StatsView scene={scene} />;
    case 'devices':
      return <DevicesView scene={scene} />;
    case 'end':
      return <EndView scene={scene} />;
  }
};
