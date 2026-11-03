import {Composition} from 'remotion';
import shotData from '../../scenes/shots/test_pick.json';
import {TestPick} from './TestPick';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="TestPick"
    component={TestPick}
    durationInFrames={shotData.frames}
    fps={shotData.fps}
    width={shotData.resolution[0]}
    height={shotData.resolution[1]}
  />
);
