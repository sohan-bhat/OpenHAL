import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {COLOR, MONO, SANS, progress} from './theme';

export type EndCardProps = {tagline: string; command: string; url: string; finePrint: string};

const rise = (frame: number, at: number, length = 14) => {
  const t = progress(frame, at, length);
  return {opacity: t, translate: `0 ${(1 - t) * 12}px`};
};

export const Wordmark: React.FC<{size: number; style?: React.CSSProperties}> = ({size, style}) => (
  <div style={{fontFamily: SANS, fontWeight: 700, fontSize: size, letterSpacing: '-0.04em', lineHeight: 1, color: COLOR.text, ...style}}>OpenHAL</div>
);

export const EndCard: React.FC<EndCardProps> = ({tagline, command, url, finePrint}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: COLOR.bg, alignItems: 'center', justifyContent: 'center'}}>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: -24}}>
        <Wordmark size={132} style={rise(frame, 2, 16)} />
        <div style={{fontFamily: MONO, fontSize: 27, color: COLOR.text, marginTop: 40, ...rise(frame, 12)}}>{tagline}</div>
        <div style={{fontFamily: MONO, fontSize: 27, color: COLOR.text, marginTop: 44, ...rise(frame, 21)}}>
          <span style={{color: COLOR.accent}}>$</span> {command}
        </div>
        <div style={{fontFamily: MONO, fontSize: 22, color: COLOR.text2, marginTop: 14, ...rise(frame, 28)}}>{url}</div>
      </div>
      <div style={{position: 'absolute', bottom: 52, fontFamily: SANS, fontSize: 17, color: COLOR.text2, ...rise(frame, 40, 18)}}>{finePrint}</div>
    </AbsoluteFill>
  );
};
