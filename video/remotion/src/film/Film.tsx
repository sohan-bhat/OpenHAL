import {AbsoluteFill, Img, OffthreadVideo, Sequence, staticFile, useVideoConfig} from 'remotion';
import {EndCard, SceneWordmark, Wordmark} from './EndCard';
import {Aspect, COLORS, Item, Label, card, film, stills} from './edit';
import {LabelView} from './Label';

const Shot: React.FC<{item: Item; aspect: Aspect}> = ({item, aspect}) => (
  <OffthreadVideo
    src={staticFile(`shots/${item.id}-${aspect}.mp4`)}
    muted
    style={{width: '100%', height: '100%', objectFit: 'cover'}}
  />
);

export type FilmProps = {aspect: Aspect};

export const Film: React.FC<FilmProps> = ({aspect}) => (
  <AbsoluteFill style={{background: COLORS.bg}}>
    {film.items.map((item) => (
      <Sequence key={item.id} from={item.start} durationInFrames={item.frames} name={item.id}>
        {item.kind === 'shot' ? <Shot item={item} aspect={aspect} /> : null}
        {item.kind === 'black' ? <AbsoluteFill style={{background: '#000'}} /> : null}
        {item.kind === 'card' ? <EndCard item={item} aspect={aspect} /> : null}
        {item.wordmark !== undefined ? (
          <Sequence from={item.wordmark} durationInFrames={item.frames - item.wordmark}>
            <SceneWordmark aspect={aspect} />
          </Sequence>
        ) : null}
      </Sequence>
    ))}
    {film.labels.map((label) => (
      <Sequence key={`${label.shot}-${label.text}`} from={label.from} durationInFrames={label.to - label.from} name={label.text}>
        <LabelView label={label} aspect={aspect} />
      </Sequence>
    ))}
  </AbsoluteFill>
);

export type StoryboardProps = {aspect: Aspect; beat: number};

const beatLabel = (shots: string[], frame: number): Label | undefined => {
  const mine = film.labels.filter((label) => shots.includes(label.shot));
  return mine.find((label) => label.from <= frame && frame < label.to) ?? mine[0];
};

export const Storyboard: React.FC<StoryboardProps> = ({aspect, beat}) => {
  const end = card();
  if (beat === end.storyboard) {
    return <EndCard item={end} aspect={aspect} still />;
  }
  const still = stills.find((s) => s.storyboard === beat);
  if (!still) {
    throw new Error(`No still for beat ${beat}`);
  }
  const item = film.items.find((i) => i.id === still.shot);
  const shots = film.items.filter((i) => i.storyboard === beat).map((i) => i.id);
  const at = (item?.start ?? 0) + still.frame - 1;
  const label = beatLabel(shots, at);
  return (
    <AbsoluteFill style={{background: COLORS.bg}}>
      <Img src={staticFile(`stills/${still.shot}-${aspect}.png`)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      {item?.wordmark !== undefined && beat === item.storyboard ? <SceneWordmark aspect={aspect} still /> : null}
      {label ? <LabelView label={label} aspect={aspect} still /> : null}
    </AbsoluteFill>
  );
};

export type ThumbnailProps = {beat: number};

export const Thumbnail: React.FC<ThumbnailProps> = ({beat}) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill>
      <Storyboard aspect="landscape" beat={beat} />
      <Wordmark height={210} style={{position: 'absolute', left: 0.07 * width, top: 0.1 * height}} />
    </AbsoluteFill>
  );
};
