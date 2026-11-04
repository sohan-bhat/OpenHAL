import {useCurrentFrame} from 'remotion';
import {EASE, clamp01} from './theme';

export type CursorKey = {at: number; x: number; y: number};

const ARROW = 'M0 0 L0 22 L5.6 16.6 L9.4 25.4 L13.2 23.8 L9.4 15.2 L16.6 15.2 Z';

const positionAt = (keys: CursorKey[], frame: number) => {
  if (frame <= keys[0].at) {
    return keys[0];
  }
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i];
    const b = keys[i + 1];
    if (frame <= b.at) {
      const t = EASE.glide(clamp01((frame - a.at) / Math.max(1, b.at - a.at)));
      return {at: frame, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t};
    }
  }
  return keys[keys.length - 1];
};

export const Cursor: React.FC<{keys: CursorKey[]; clicks: number[]; appear?: number}> = ({keys, clicks, appear = 0}) => {
  const frame = useCurrentFrame();
  const {x, y} = positionAt(keys, frame);
  const press = clicks.reduce((p, at) => {
    const d = frame - at;
    return d >= 0 && d < 8 ? Math.max(p, 1 - Math.abs(d - 2) / 6) : p;
  }, 0);
  const opacity = clamp01((frame - appear) / 6);
  return (
    <svg
      width={34}
      height={44}
      viewBox="-2 -2 22 30"
      style={{position: 'absolute', left: x - 2.4, top: y - 2.4, opacity, scale: `${1 - 0.14 * press}`, transformOrigin: '2px 2px', overflow: 'visible'}}
    >
      <path d={ARROW} fill="#111210" stroke="#ffffff" strokeWidth={1.6} strokeLinejoin="round" />
    </svg>
  );
};
