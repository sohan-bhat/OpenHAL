import {Composition, Still} from 'remotion';
import shotData from '../../scenes/shots/test_pick.json';
import {Compare, CompareProps} from './Compare';
import {TestPick} from './TestPick';

const compareDefaults: CompareProps = {
  panels: [
    {image: 'compare/cycles.png', title: 'Blender Cycles', detail: 'CPU path tracing'},
    {image: 'compare/eevee.png', title: 'Blender EEVEE', detail: 'GPU raster with ray tracing'},
    {image: 'compare/remotion.png', title: 'Remotion and three.js', detail: 'WebGL through ANGLE'},
  ],
  crop: {x: 1580, y: 760},
  caption: 'Shot frame 94 at 3840 by 2160. Lower row at 100 percent.',
};

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="TestPick"
      component={TestPick}
      durationInFrames={shotData.frames}
      fps={shotData.fps}
      width={shotData.resolution[0]}
      height={shotData.resolution[1]}
    />
    <Still id="Compare" component={Compare} width={3840} height={2160} defaultProps={compareDefaults} />
  </>
);
