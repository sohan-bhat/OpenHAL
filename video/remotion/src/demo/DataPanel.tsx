import {COLOR, MONO, SANS, progress} from './theme';

export type Verdict = {text: string; color: string; at: number};

export type DataPanelProps = {
  frame: number;
  title: string;
  subtitle: string;
  label: string;
  value: number;
  unit: string;
  decimals?: number;
  limit: number;
  scaleMax: number;
  limitLabel: string;
  verdict?: Verdict | null;
  overColor?: string;
  offset?: number;
};

const fmt = (value: number, decimals: number) =>
  value.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});

export const DataPanel: React.FC<DataPanelProps> = ({
  frame,
  title,
  subtitle,
  label,
  value,
  unit,
  decimals = 0,
  limit,
  scaleMax,
  limitLabel,
  verdict,
  overColor = COLOR.blocked,
  offset = 0,
}) => {
  const head = progress(frame, 0, 14);
  const body = progress(frame, 6, 14);
  const bar = progress(frame, 10, 16);
  const width = 360;
  const fraction = Math.min(1, Math.max(0, value / scaleMax));
  const limitAt = limit / scaleMax;
  const under = Math.min(fraction, limitAt);
  const over = Math.max(0, fraction - limitAt);
  const shown = verdict ? progress(frame, verdict.at, 10) : 0;
  return (
    <div style={{position: 'absolute', left: 80, top: offset, width, height: '100%', color: COLOR.text}}>
      <div style={{position: 'absolute', top: 104, opacity: head, translate: `0 ${(1 - head) * 10}px`}}>
        <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 46, letterSpacing: '-0.02em', lineHeight: 1.08}}>{title}</div>
        <div style={{fontFamily: MONO, fontSize: 23, color: COLOR.text2, marginTop: 12}}>{subtitle}</div>
      </div>
      <div style={{position: 'absolute', top: 300, opacity: body, translate: `0 ${(1 - body) * 10}px`}}>
        <div style={{fontFamily: MONO, fontSize: 24, color: COLOR.text2}}>{label}</div>
        <div style={{display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 6}}>
          <span style={{fontFamily: MONO, fontWeight: 400, fontSize: 84, letterSpacing: '-0.03em', lineHeight: 1, fontVariantNumeric: 'tabular-nums'}}>
            {fmt(value, decimals)}
          </span>
          <span style={{fontFamily: MONO, fontSize: 26, color: COLOR.text2}}>{unit}</span>
        </div>
      </div>
      <div style={{position: 'absolute', top: 432, width, opacity: bar}}>
        <div style={{position: 'relative', height: 8, background: COLOR.border}}>
          <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: `${under * 100}%`, background: COLOR.text2}} />
          <div style={{position: 'absolute', left: `${limitAt * 100}%`, top: 0, bottom: 0, width: `${over * 100}%`, background: overColor}} />
          <div style={{position: 'absolute', left: `${limitAt * 100}%`, top: -7, height: 22, width: 2, marginLeft: -1, background: COLOR.text}} />
        </div>
        <div
          style={{
            position: 'absolute',
            left: `${limitAt * 100}%`,
            top: 24,
            translate: '-50% 0',
            whiteSpace: 'nowrap',
            fontFamily: MONO,
            fontSize: 23,
            color: COLOR.text2,
          }}
        >
          {limitLabel}
        </div>
      </div>
      {verdict ? (
        <div
          style={{
            position: 'absolute',
            top: 520,
            fontFamily: MONO,
            fontWeight: 700,
            fontSize: 44,
            letterSpacing: '0.01em',
            color: verdict.color,
            opacity: shown,
            translate: `0 ${(1 - shown) * 8}px`,
          }}
        >
          {verdict.text}
        </div>
      ) : null}
    </div>
  );
};
