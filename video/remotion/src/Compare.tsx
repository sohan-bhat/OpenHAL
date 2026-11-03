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
const COLUMN = 1280;
const FRAME = 720;
const CROP = 1300;

export const Compare: React.FC<CompareProps> = ({panels, crop, caption}) => (
  <AbsoluteFill style={{backgroundColor: look.palette.backdrop, fontFamily: SANS, color: TEXT}}>
    <div style={{display: 'flex', height: FRAME}}>
      {panels.map((panel) => (
        <Img key={panel.image} src={staticFile(panel.image)} style={{width: COLUMN, height: FRAME, display: 'block'}} />
      ))}
    </div>
    <div style={{display: 'flex', height: CROP, borderTop: `2px solid ${RULE}`}}>
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
            style={{position: 'absolute', left: -crop.x, top: -crop.y, width: 3840, height: 2160, maxWidth: 'none'}}
          />
        </div>
      ))}
    </div>
    <div style={{display: 'flex', height: 2160 - FRAME - CROP, borderTop: `2px solid ${RULE}`}}>
      {panels.map((panel) => (
        <div key={panel.image} style={{width: COLUMN, padding: '28px 40px', boxSizing: 'border-box'}}>
          <div style={{fontSize: 44, fontWeight: 600, letterSpacing: -0.4}}>{panel.title}</div>
          <div style={{fontFamily: MONO, fontSize: 26, color: MUTED, marginTop: 12, lineHeight: 1.45}}>{panel.detail}</div>
        </div>
      ))}
    </div>
    <div style={{position: 'absolute', right: 40, bottom: 24, fontFamily: MONO, fontSize: 22, color: MUTED}}>{caption}</div>
  </AbsoluteFill>
);
