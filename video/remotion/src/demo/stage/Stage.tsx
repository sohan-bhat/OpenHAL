import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {CameraPose} from '../Arm3D';
import {Cursor, CursorKey} from '../Cursor';
import {CameraMove, cameraAt} from '../DeskScene';
import {Mascot} from '../Mascot';
import {poseOf} from '../edit';
import {Vec3} from '../recording';
import {COLOR, EASE, MONO, SANS, clamp01, progress} from '../theme';
import {LAYER, LAYER_DISTANCE, PATH_TOTAL, PULSE_PATH, PulseState, WedgeState, World, pointAt, projectPoint} from './World';

const WIDTH = 1280;
const HEIGHT = 720;

export type Tone = 'ok' | 'blocked' | 'pending' | 'text';
const TONE: Record<Tone, string> = {ok: COLOR.ok, blocked: COLOR.blocked, pending: COLOR.confirm, text: COLOR.text};

export type PromptSpec = {text: string; at: number; submit: number; cps: number; timer?: {from: number; to: number; until: number}};
export type PulseSpec = {tool: string; at: number; layerAt: number; holdUntil?: number; arriveAt?: number; blocked?: boolean};
export type AnswerSpec = {word: string; tone: Tone; at: number; until?: number; lift?: number; dx?: number};
export type CardSpec = {kind: 'approve' | 'stop'; label: string; at: number; press: number; cursor: CursorKey[]};
export type LimitSpec = {at: number; ghostFrom: number[]; ghostTo: number[]; requested: number; sweepDeg: number};

export type StageSpec = {
  id: string;
  kind: 'stage';
  from: number;
  frames: number;
  poses: number[][];
  speeds: number[];
  shots: {start: number; camera: CameraMove}[];
  prompt?: PromptSpec;
  pulse?: PulseSpec;
  answer?: AnswerSpec;
  card?: CardSpec;
  limit?: LimitSpec;
  flatAt?: number;
};

const SPINNER = ['·', '✢', '✳', '✶', '✻', '✽', '✻', '✶', '✳', '✢'];

const cameraOf = (spec: StageSpec, frame: number): CameraPose => {
  const shot = spec.shots.filter((s) => frame >= s.start).pop() ?? spec.shots[0];
  return cameraAt(shot.camera, frame - shot.start);
};

const pulseOf = (spec: PulseSpec | undefined, frame: number): PulseState | null => {
  if (!spec || frame < spec.at) {
    return null;
  }
  const toLayer = EASE.inOut(clamp01((frame - spec.at) / Math.max(1, spec.layerAt - spec.at)));
  let head = toLayer * LAYER_DISTANCE;
  let color: string = COLOR.accent;
  let visible = 1;
  if (spec.blocked) {
    color = frame >= spec.layerAt ? COLOR.blocked : COLOR.accent;
  } else {
    const release = spec.holdUntil ?? spec.layerAt;
    const arrive = spec.arriveAt ?? release + 14;
    if (frame >= release) {
      head = LAYER_DISTANCE + EASE.inOut(clamp01((frame - release) / Math.max(1, arrive - release))) * (PATH_TOTAL - LAYER_DISTANCE);
    }
    visible = 1 - clamp01((frame - arrive) / 10);
  }
  return {head: head + 0.035 * Math.min(1, toLayer * 4), color, visible};
};

const limitOf = (spec: LimitSpec | undefined, frame: number): WedgeState | null => {
  if (!spec || frame < spec.at) {
    return null;
  }
  const show = progress(frame, spec.at, 10);
  const start = spec.at + 12;
  const deltas = spec.ghostTo.map((v, i) => v - spec.ghostFrom[i]);
  const longest = Math.max(...deltas.slice(0, 5).map(Math.abs));
  const pan = Math.abs(deltas[0]) || 1;
  const stopAt = Math.min(1, spec.sweepDeg / pan);
  const seconds = Math.max(0, (frame - start) / 30);
  const f = Math.min(stopAt, (seconds * spec.requested) / (longest || 1));
  const ghost = frame >= start ? spec.ghostFrom.map((v, i) => (i < 5 ? v + deltas[i] * f : v)) : null;
  const hit = f >= stopAt - 1e-6 && frame >= start ? 1 : 0;
  return {show, sweep: Math.sign(deltas[0]) * spec.sweepDeg * (Math.PI / 180), ghost, ghostShow: frame >= start ? 1 : 0, hit};
};

const Prompt: React.FC<{spec: PromptSpec; frame: number}> = ({spec, frame}) => {
  const shown = progress(frame, spec.at - 8, 10);
  const count = Math.max(0, Math.floor(((frame - spec.at) / 30) * spec.cps));
  const text = spec.text.slice(0, Math.min(spec.text.length, count));
  const submitted = frame >= spec.submit;
  const timer = spec.timer && submitted && frame < spec.timer.until;
  const elapsed = spec.timer ? spec.timer.from + clamp01((frame - spec.submit) / Math.max(1, spec.timer.until - spec.submit)) * (spec.timer.to - spec.timer.from) : 0;
  return (
    <div
      style={{
        position: 'absolute',
        left: 130,
        right: 130,
        bottom: 34,
        minHeight: 58,
        paddingTop: 12,
        paddingBottom: 12,
        boxSizing: 'border-box',
        lineHeight: 1.35,
        borderRadius: 6,
        background: COLOR.surface,
        boxShadow: `inset 0 0 0 1px ${COLOR.border}`,
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        padding: '0 22px',
        fontFamily: MONO,
        fontSize: 23,
        color: COLOR.text,
        opacity: shown,
        translate: `0 ${(1 - shown) * 12}px`,
      }}
    >
      <Mascot cell={17} color={COLOR.claude} />
      <span style={{color: COLOR.text2}}>&gt;</span>
      <span style={{flex: 1, whiteSpace: 'normal', color: submitted ? COLOR.text2 : COLOR.text}}>
        {text}
        {!submitted ? <span style={{display: 'inline-block', width: '0.6em', height: '1.1em', verticalAlign: '-0.2em', background: COLOR.text, marginLeft: 2}} /> : null}
      </span>
      {timer ? (
        <span style={{color: COLOR.claude, whiteSpace: 'nowrap'}}>
          {SPINNER[Math.floor(frame / 3) % SPINNER.length]} {Math.floor(elapsed)}s
        </span>
      ) : null}
    </div>
  );
};

const Card: React.FC<{spec: CardSpec; frame: number}> = ({spec, frame}) => {
  const shown = progress(frame, spec.at, 10);
  const d = frame - spec.press;
  const press = d >= 0 && d < 8 ? 1 - Math.abs(d - 2) / 6 : 0;
  const pressed = frame >= spec.press;
  const stop = spec.kind === 'stop';
  return (
    <div
      style={{
        position: 'absolute',
        left: 48,
        top: 48,
        padding: 18,
        borderRadius: 6,
        background: COLOR.bg,
        boxShadow: `inset 0 0 0 1px ${COLOR.border}`,
        opacity: shown,
        translate: `0 ${(1 - shown) * -10}px`,
      }}
    >
      <div
        style={{
          padding: stop ? '12px 34px' : '12px 22px',
          borderRadius: 6,
          background: stop ? COLOR.blocked : pressed ? '#de51a8' : COLOR.accentFill,
          boxShadow: stop ? `inset 0 0 0 ${2 + press}px ${COLOR.bg}` : `inset 0 0 0 1.5px ${COLOR.accent}`,
          border: stop ? `2px solid ${COLOR.blocked}` : undefined,
          color: stop ? COLOR.bg : COLOR.onAccent,
          fontFamily: SANS,
          fontWeight: 700,
          fontSize: stop ? 30 : 22,
          letterSpacing: stop ? '0.08em' : '-0.01em',
          scale: `${1 - 0.04 * press}`,
        }}
      >
        {spec.label}
      </div>
    </div>
  );
};

const Label: React.FC<{at: [number, number]; text: string; color: string; opacity: number; size: number; weight?: number}> = ({at, text, color, opacity, size, weight = 600}) => (
  <div
    style={{
      position: 'absolute',
      left: at[0],
      top: at[1],
      translate: '-50% -100%',
      fontFamily: MONO,
      fontWeight: weight,
      fontSize: size,
      color,
      opacity,
      whiteSpace: 'nowrap',
      textShadow: `0 0 0.5em ${COLOR.bg}, 0 0 0.25em ${COLOR.bg}`,
    }}
  >
    {text}
  </div>
);

export const Stage: React.FC<{spec: StageSpec}> = ({spec}) => {
  const frame = useCurrentFrame();
  const i = Math.min(spec.poses.length - 1, Math.max(0, frame));
  const camera = cameraOf(spec, frame);
  const pulse = pulseOf(spec.pulse, frame);
  const limit = limitOf(spec.limit, frame);
  const flat = spec.flatAt !== undefined ? progress(frame, spec.flatAt, 8, EASE.out) : 0;
  const head: Vec3 | null = pulse ? pointAt(pulse.head) : null;
  const headScreen = head ? projectPoint(camera, [head[0], head[1], head[2] + 0.02], WIDTH, HEIGHT) : null;
  const layerScreen = projectPoint(camera, [PULSE_PATH[1][0], LAYER.y, spec.answer?.lift ?? 0.11], WIDTH, HEIGHT);
  const answer = spec.answer;
  const answerShow = answer ? progress(frame, answer.at, 8) * (answer.until !== undefined ? 1 - progress(frame, answer.until, 8) : 1) : 0;
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <World width={WIDTH} height={HEIGHT} pose={poseOf(spec.poses[i])} camera={camera} flat={flat} pulse={pulse} wedge={limit} />
      {pulse && headScreen && spec.pulse ? (
        <Label at={[headScreen[0], headScreen[1] - 10]} text={spec.pulse.tool} color={pulse.color} opacity={pulse.visible * clamp01((600 - headScreen[1]) / 40)} size={24} />
      ) : null}
      {answer && answerShow > 0 ? <Label at={[layerScreen[0] + (answer.dx ?? 0), layerScreen[1] - 8]} text={answer.word} color={TONE[answer.tone]} opacity={answerShow} size={34} weight={700} /> : null}
      {spec.card ? <Card spec={spec.card} frame={frame} /> : null}
      {spec.prompt ? <Prompt spec={spec.prompt} frame={frame} /> : null}
      {spec.card ? <Cursor keys={spec.card.cursor} clicks={[spec.card.press]} appear={spec.card.at} /> : null}
    </AbsoluteFill>
  );
};
