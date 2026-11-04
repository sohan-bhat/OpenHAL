import {useCurrentFrame, useVideoConfig} from 'remotion';
import beatPick from '../../../data/beat-2-pick-and-place.json';
import {DataPanel} from './DataPanel';
import {DESK_CAMERA, DeskScene, cameraAt} from './DeskScene';
import {Beat, Track, clipTime} from './recording';
import {COLOR} from './theme';

const track = new Track([beatPick as unknown as Beat]);

export const DeskTest: React.FC<{start: number}> = ({start}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = clipTime({track, start, speed: 1, fps}, frame);
  const fastest = track.fastestJoint(t);
  return (
    <DeskScene
      pose={track.pose(t)}
      camera={cameraAt(DESK_CAMERA, frame + 60)}
      panel={
        <DataPanel
          frame={frame + 30}
          title="SO-101 arm"
          subtitle="so101-sim.hal.yaml"
          label="Fastest joint"
          value={fastest.speed}
          unit="deg/s"
          limit={60}
          scaleMax={100}
          limitLabel="60 deg/s max"
          verdict={{text: 'done', color: COLOR.ok, at: 40}}
        />
      }
    />
  );
};
