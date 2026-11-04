import {useCurrentFrame} from 'remotion';
import {COLOR, MONO, SANS, TIME, progress} from './theme';

export type Stat = {value: number; decimals?: number; unit: string; label: string};

const fmt = (value: number, decimals: number) =>
  value.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});

export const StatCard: React.FC<{stat: Stat; at: number}> = ({stat, at}) => {
  const frame = useCurrentFrame();
  const shown = progress(frame, at, TIME.appear);
  const count = progress(frame, at, TIME.countUp);
  return (
    <div style={{opacity: shown, translate: `0 ${(1 - shown) * 14}px`}}>
      <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
        <span style={{fontFamily: MONO, fontWeight: 600, fontSize: 150, letterSpacing: '-0.05em', lineHeight: 1, color: COLOR.text, fontVariantNumeric: 'tabular-nums'}}>
          {fmt(stat.value * count, stat.decimals ?? 0)}
        </span>
        <span style={{fontFamily: MONO, fontSize: 46, color: COLOR.text2}}>{stat.unit}</span>
      </div>
      <div style={{width: 120, height: 3, background: COLOR.accent, marginTop: 22, scale: `${count} 1`, transformOrigin: 'left'}} />
      <div style={{fontFamily: SANS, fontWeight: 500, fontSize: 30, lineHeight: 1.3, color: COLOR.text, marginTop: 22, maxWidth: 440}}>{stat.label}</div>
    </div>
  );
};

export type Device = {name: string; file: string; lines: string[]; status?: {word: string; at: number}};

export const DeviceCard: React.FC<{device: Device; at: number}> = ({device, at}) => {
  const frame = useCurrentFrame();
  const shown = progress(frame, at, TIME.appear);
  const status = device.status ? progress(frame, device.status.at, 8) : 0;
  return (
    <div
      style={{
        flex: '1 1 0',
        padding: '32px 30px 30px',
        borderRadius: 6,
        background: COLOR.surface,
        boxShadow: `inset 0 0 0 1px ${COLOR.border}`,
        opacity: shown,
        translate: `0 ${(1 - shown) * 24}px`,
      }}
    >
      <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 36, letterSpacing: '-0.02em', color: COLOR.text, lineHeight: 1.12, minHeight: 81}}>{device.name}</div>
      <div style={{fontFamily: MONO, fontSize: 22, color: COLOR.text2, marginTop: 14, whiteSpace: 'nowrap'}}>{device.file}</div>
      <div style={{height: 1, background: COLOR.border, margin: '22px 0 20px'}} />
      <div style={{fontFamily: MONO, fontSize: 24, lineHeight: 1.55, color: COLOR.text, whiteSpace: 'pre'}}>
        {device.lines.map((line, i) => {
          const colon = line.indexOf(':');
          return (
            <div key={i}>
              {colon > 0 ? (
                <>
                  <span style={{color: COLOR.text2}}>{line.slice(0, colon + 1)}</span>
                  {line.slice(colon + 1)}
                </>
              ) : (
                line
              )}
            </div>
          );
        })}
      </div>
      {device.status ? (
        <div style={{fontFamily: MONO, fontWeight: 700, fontSize: 24, color: COLOR.ok, marginTop: 16, opacity: status}}>{device.status.word}</div>
      ) : null}
    </div>
  );
};
