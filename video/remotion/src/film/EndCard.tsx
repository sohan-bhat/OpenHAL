import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Aspect, COLORS, Item, MONO, SANS, easeOut} from './edit';

const WORDMARK_RATIO = 163 / 44;

const appear = (frame: number, at: number, length = 16) => {
  const t = easeOut((frame - at) / length);
  return {opacity: t, transform: `translateY(${(1 - t) * 0.35}em)`};
};

export const Wordmark: React.FC<{height: number; style?: React.CSSProperties}> = ({height, style}) => (
  <Img src={staticFile('brand/wordmark-dark.svg')} style={{height, width: height * WORDMARK_RATIO, display: 'block', ...style}} />
);

export const SceneWordmark: React.FC<{aspect: Aspect; still?: boolean}> = ({aspect, still}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const t = still ? 1 : easeOut(frame / 14);
  const h = aspect === 'landscape' ? 74 : 84;
  const style: React.CSSProperties =
    aspect === 'landscape'
      ? {position: 'absolute', left: 0.07 * width, top: 0.83 * height - h / 2}
      : {position: 'absolute', left: (width - h * WORDMARK_RATIO) / 2, top: 0.17 * height - h / 2};
  return <Wordmark height={h} style={{...style, opacity: t}} />;
};

export const EndCard: React.FC<{item: Item; aspect: Aspect; still?: boolean}> = ({item, aspect, still}) => {
  const current = useCurrentFrame();
  const {width} = useVideoConfig();
  const frame = still ? item.frames - 20 : current;
  const vertical = aspect === 'vertical';
  const mark = vertical ? 230 : 250;
  const line = easeOut(frame / 26);
  const out = still ? 1 : Math.min(1, Math.max(0, (item.frames - frame) / 14));
  return (
    <AbsoluteFill
      style={{
        background: COLORS.bg,
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: SANS,
        color: COLORS.text,
        opacity: out,
      }}
    >
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', width: vertical ? '82%' : '70%'}}>
        <div style={{fontSize: mark, ...appear(frame, 8, 20)}}>
          <Wordmark height={mark} />
        </div>
        <div
          style={{
            width: vertical ? width * 0.62 : width * 0.36,
            height: 5,
            margin: vertical ? '110px 0 100px' : '96px 0 88px',
            background: COLORS.accent,
            transform: `scaleX(${line})`,
          }}
        />
        <div
          style={{
            fontSize: vertical ? 108 : 100,
            fontWeight: 400,
            lineHeight: 1.25,
            letterSpacing: '-0.012em',
            textAlign: 'center',
            color: COLORS.text,
            textWrap: 'balance',
            ...appear(frame, 26),
          }}
        >
          {item.tagline}
        </div>
        <div
          style={{
            marginTop: vertical ? 150 : 120,
            fontFamily: MONO,
            fontWeight: 600,
            fontSize: vertical ? 104 : 92,
            color: COLORS.text,
            ...appear(frame, 44),
          }}
        >
          <span style={{color: COLORS.text2}}>$ </span>
          {item.command}
        </div>
        <div
          style={{
            marginTop: vertical ? 54 : 44,
            fontFamily: MONO,
            fontWeight: 400,
            fontSize: vertical ? 78 : 70,
            color: COLORS.text2,
            ...appear(frame, 56),
          }}
        >
          {item.url}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: vertical ? 260 : 150,
          fontSize: vertical ? 50 : 46,
          color: COLORS.muted,
          letterSpacing: '0.005em',
          ...appear(frame, 80, 20),
        }}
      >
        {item.fine_print}
      </div>
    </AbsoluteFill>
  );
};
