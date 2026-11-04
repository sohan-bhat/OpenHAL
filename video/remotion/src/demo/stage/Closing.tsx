import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Wordmark} from '../EndCard';
import {COLOR, EASE, MONO, SANS, progress} from '../theme';

const LINE_Y = 372;

const LayerLine: React.FC<{frame: number; y?: number; at?: number}> = ({frame, y = LINE_Y, at = 0}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      right: 0,
      top: y,
      height: 2,
      background: COLOR.accent,
      scale: `${progress(frame, at, 18, EASE.inOut)} 1`,
      transformOrigin: 'left',
    }}
  />
);

const rise = (frame: number, at: number, length = 12) => {
  const t = progress(frame, at, length);
  return {opacity: t, translate: `0 ${(1 - t) * 14}px`};
};

export type StatSpec = {value: number; decimals: number; unit: string; label?: string};
export type StatsScene = {id: string; kind: 'stats'; from: number; frames: number; stats: StatSpec[]};
export type DevicesScene = {id: string; kind: 'devices'; from: number; frames: number; files: string[]};
export type EndScene = {id: string; kind: 'end'; from: number; frames: number; tagline: string; command: string; url: string; finePrint: string};

const fmt = (value: number, decimals: number) => value.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});

export const Stats: React.FC<{scene: StatsScene}> = ({scene}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <LayerLine frame={frame} />
      {scene.stats.map((stat, i) => {
        const at = 6 + i * 14;
        const count = progress(frame, at, 22);
        const left = 120 + i * 560;
        return (
          <div key={stat.unit} style={{position: 'absolute', left, top: 0}}>
            <div style={{position: 'absolute', top: LINE_Y - 196, display: 'flex', alignItems: 'baseline', gap: 16, whiteSpace: 'nowrap', ...rise(frame, at)}}>
              <span style={{fontFamily: SANS, fontWeight: 700, fontSize: 176, letterSpacing: '-0.05em', lineHeight: 1, color: COLOR.text, fontVariantNumeric: 'tabular-nums'}}>
                {fmt(stat.value * count, stat.decimals)}
              </span>
              <span style={{fontFamily: MONO, fontSize: 52, color: COLOR.text2}}>{stat.unit}</span>
            </div>
            {stat.label ? (
              <div style={{position: 'absolute', top: LINE_Y + 30, fontFamily: SANS, fontWeight: 500, fontSize: 38, color: COLOR.text, whiteSpace: 'nowrap', ...rise(frame, at + 8)}}>{stat.label}</div>
            ) : null}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const Devices: React.FC<{scene: DevicesScene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const y = 170;
  const bus = 150;
  const rows = scene.files.map((_, i) => y + 130 + i * 120);
  const down = progress(frame, 8, 16, EASE.inOut);
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <LayerLine frame={frame} y={y} />
      <div style={{position: 'absolute', left: bus, top: y + 2, width: 2, height: (rows[rows.length - 1] - y) * down, background: COLOR.text2}} />
      {scene.files.map((file, i) => {
        const at = 14 + i * 8;
        const reach = progress(frame, at, 10, EASE.inOut);
        return (
          <div key={file}>
            <div style={{position: 'absolute', left: bus, top: rows[i], width: 90 * reach, height: 2, background: COLOR.text2}} />
            <div style={{position: 'absolute', left: bus + 118, top: rows[i] - 30, fontFamily: MONO, fontWeight: 600, fontSize: 48, color: COLOR.text, whiteSpace: 'nowrap', ...rise(frame, at + 6)}}>{file}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const End: React.FC<{scene: EndScene}> = ({scene}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <LayerLine frame={frame} at={4} />
      <div style={{position: 'absolute', left: 120, top: LINE_Y - 170, ...rise(frame, 2, 16)}}>
        <Wordmark size={150} />
      </div>
      <div style={{position: 'absolute', left: 124, top: LINE_Y + 38, fontFamily: SANS, fontSize: 34, color: COLOR.text, ...rise(frame, 14)}}>{scene.tagline}</div>
      <div style={{position: 'absolute', left: 124, top: LINE_Y + 110, display: 'flex', gap: 48, fontFamily: MONO, fontSize: 30, ...rise(frame, 24)}}>
        <span style={{color: COLOR.text}}>
          <span style={{color: COLOR.accent}}>$</span> {scene.command}
        </span>
        <span style={{color: COLOR.text2}}>{scene.url}</span>
      </div>
      <div style={{position: 'absolute', left: 124, bottom: 46, fontFamily: SANS, fontSize: 21, color: COLOR.text2, ...rise(frame, 40, 18)}}>{scene.finePrint}</div>
    </AbsoluteFill>
  );
};
