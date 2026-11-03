import {loadFont} from '@remotion/fonts';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import look from '../../scenes/look.json';

const MONO = 'IBM Plex Mono';
const SANS = 'IBM Plex Sans';

loadFont({family: MONO, url: staticFile('fonts/ibm-plex-mono-latin-400-normal.woff2'), weight: '400'});
loadFont({family: SANS, url: staticFile('fonts/ibm-plex-sans-latin-wght-normal.woff2'), weight: '100 700'});

export type ComparePanel = {image: string; title: string; detail: string};

export type CompareProps = {
  panels: ComparePanel[];
  crop: {x: number; y: number};
  caption: string;
};

const TEXT = '#eceeec';
const MUTED = '#afb5ad';
const RULE = '#383a36';
const WIDTH = 3840;
const HEIGHT = 2160;
const COLUMN = 1280;
const FRAME = 720;
const INFO = 210;
const STRIP = 64;
const CROP = HEIGHT - FRAME - INFO - STRIP;

export const Compare: React.FC<CompareProps> = ({panels, crop, caption}) => (
  <AbsoluteFill style={{backgroundColor: look.palette.backdrop, fontFamily: SANS, color: TEXT}}>
    <div style={{display: 'flex', height: FRAME}}>
      {panels.map((panel) => (
        <Img key={panel.image} src={staticFile(panel.image)} style={{width: COLUMN, height: FRAME, display: 'block'}} />
      ))}
    </div>
    <div style={{display: 'flex', height: INFO, borderTop: `2px solid ${RULE}`, boxSizing: 'border-box'}}>
      {panels.map((panel) => (
        <div key={panel.image} style={{width: COLUMN, padding: '26px 40px', boxSizing: 'border-box'}}>
          <div style={{fontSize: 44, fontWeight: 600, letterSpacing: -0.4, lineHeight: 1.2}}>{panel.title}</div>
          <div style={{fontFamily: MONO, fontSize: 26, color: MUTED, marginTop: 10, lineHeight: 1.45, whiteSpace: 'pre-line'}}>
            {panel.detail}
          </div>
        </div>
      ))}
    </div>
    <div
      style={{
        height: STRIP,
        display: 'flex',
        alignItems: 'center',
        padding: '0 40px',
        borderTop: `2px solid ${RULE}`,
        boxSizing: 'border-box',
        fontFamily: MONO,
        fontSize: 24,
        color: MUTED,
      }}
    >
      {caption}
    </div>
    <div style={{display: 'flex', height: CROP, borderTop: `2px solid ${RULE}`, boxSizing: 'border-box'}}>
      {panels.map((panel, i) => (
        <div
          key={panel.image}
          style={{
            position: 'relative',
            width: COLUMN,
            height: CROP,
            overflow: 'hidden',
            borderLeft: i === 0 ? 'none' : `2px solid ${RULE}`,
          }}
        >
          <Img
            src={staticFile(panel.image)}
            style={{position: 'absolute', left: -crop.x, top: -crop.y, width: WIDTH, height: HEIGHT, maxWidth: 'none'}}
          />
        </div>
      ))}
    </div>
  </AbsoluteFill>
);
