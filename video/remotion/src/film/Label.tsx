import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Aspect, COLORS, Label as LabelData, MONO, easeOut} from './edit';

const SIZE: Record<Aspect, number> = {landscape: 104, vertical: 96};
const STOP_SIZE: Record<Aspect, number> = {landscape: 280, vertical: 250};

const color = (style: LabelData['style']): string =>
  ({call: COLORS.text, blocked: COLORS.blocked, pending: COLORS.confirm, approved: COLORS.ok, stop: COLORS.blocked})[style];

export const LabelView: React.FC<{label: LabelData; aspect: Aspect; still?: boolean}> = ({label, aspect, still}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const length = label.to - label.from;
  const stop = label.style === 'stop';
  const fadeIn = still || stop ? 1 : easeOut(frame / 7);
  const fadeOut = still ? 1 : Math.min(1, Math.max(0, (length - frame) / 6));
  const opacity = Math.min(fadeIn, stop && !still ? 1 : fadeOut);
  const rise = (1 - fadeIn) * 0.22;
  const ruleGrow = still ? 1 : easeOut(frame / 10);
  const [px, py] = label.place[aspect];
  const centered = px > 0.3;
  const size = stop ? STOP_SIZE[aspect] : SIZE[aspect];
  const [head, ...rest] = label.text.split(' ');
  return (
    <div
      style={{
        position: 'absolute',
        left: px * width,
        top: py * height,
        transform: `translate(${centered ? '-50%' : '0'}, -50%) translateY(${rise}em)`,
        fontSize: size,
        opacity,
        display: 'flex',
        flexDirection: 'column',
        alignItems: centered ? 'center' : 'flex-start',
      }}
    >
      <div
        style={{
          width: stop ? '0.9em' : '1.25em',
          height: Math.max(4, size * 0.045),
          background: stop ? COLORS.blocked : COLORS.accent,
          marginBottom: '0.32em',
          transform: `scaleX(${ruleGrow})`,
          transformOrigin: centered ? 'center' : 'left',
        }}
      />
      <div
        style={{
          fontFamily: MONO,
          fontWeight: 600,
          letterSpacing: stop ? '0.04em' : '-0.01em',
          lineHeight: 1,
          whiteSpace: 'nowrap',
          color: color(label.style),
          textShadow: '0 0 0.6em rgba(17, 18, 16, 0.85)',
        }}
      >
        {rest.length > 0 ? (
          <>
            <span style={{color: COLORS.text2}}>{head}</span> {rest.join(' ')}
          </>
        ) : (
          label.text
        )}
      </div>
    </div>
  );
};
