import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Mascot} from './Mascot';
import {COLOR, MONO, SANS, progress} from './theme';

export type Tone = 'text' | 'muted' | 'ok' | 'blocked' | 'pending';

export type Span = {text: string; tone?: Tone; bold?: boolean};

export type TerminalBlock =
  | {kind: 'prompt'; text: string; at: number; submit: number; cps?: number}
  | {kind: 'text'; spans: Span[]; at: number}
  | {
      kind: 'tool';
      server: string;
      tool: string;
      args: string;
      at: number;
      brand?: boolean;
      result?: {spans: Span[]; at: number};
    }
  | {kind: 'spinner'; word: string; at: number; until: number; elapsed?: [number, number]};

export type TerminalHeader = {title: string; model: string; cwd: string};

const TONE: Record<Tone, string> = {
  text: COLOR.text,
  muted: COLOR.text2,
  ok: COLOR.ok,
  blocked: COLOR.blocked,
  pending: COLOR.confirm,
};

const FONT = 19;
const LINE = 1.5;
const SPINNER = ['·', '✢', '✳', '✶', '✻', '✽', '✻', '✶', '✳', '✢'];

const Spans: React.FC<{spans: Span[]}> = ({spans}) => (
  <>
    {spans.map((span, i) => (
      <span key={i} style={{color: TONE[span.tone ?? 'text'], fontWeight: span.bold ? 700 : 400}}>
        {span.text}
      </span>
    ))}
  </>
);

const Caret: React.FC<{frame: number; solid?: boolean}> = ({frame, solid}) => (
  <span
    style={{
      display: 'inline-block',
      width: '0.6em',
      height: '1.2em',
      verticalAlign: '-0.22em',
      background: COLOR.text,
      opacity: solid || Math.floor(frame / 16) % 2 === 0 ? 1 : 0,
    }}
  />
);

const typed = (text: string, frame: number, at: number, cps: number) => {
  const count = Math.max(0, Math.floor(((frame - at) / 30) * cps));
  return text.slice(0, Math.min(text.length, count));
};

const formatElapsed = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
};

const Row: React.FC<{marker: React.ReactNode; children: React.ReactNode; style?: React.CSSProperties}> = ({marker, children, style}) => (
  <div style={{display: 'grid', gridTemplateColumns: '1.6em 1fr', ...style}}>
    <span>{marker}</span>
    <span style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{children}</span>
  </div>
);

const ToolCall: React.FC<{block: Extract<TerminalBlock, {kind: 'tool'}>; frame: number}> = ({block, frame}) => {
  const shown = progress(frame, block.at, 8);
  const done = block.result && frame >= block.result.at;
  return (
    <div
      style={{
        position: 'relative',
        padding: block.brand ? '8px 14px 8px 10px' : 0,
        margin: block.brand ? '4px -14px 4px -10px' : 0,
        borderRadius: 6,
        boxShadow: block.brand ? `inset 0 0 0 1.5px ${COLOR.accent}` : undefined,
        opacity: shown,
      }}
    >
      {block.brand ? (
        <div
          style={{
            position: 'absolute',
            right: 12,
            top: -13,
            padding: '2px 9px 3px',
            borderRadius: 4,
            background: COLOR.accentFill,
            color: COLOR.onAccent,
            fontFamily: SANS,
            fontWeight: 700,
            fontSize: 15,
            letterSpacing: '-0.02em',
          }}
        >
          OpenHAL
        </div>
      ) : null}
      <Row marker={<span style={{color: done ? COLOR.text : COLOR.text2}}>●</span>}>
        <span style={{fontWeight: 700}}>
          {block.server} - {block.tool} (MCP)
        </span>
        <span style={{color: COLOR.text}}>({block.args})</span>
      </Row>
      {done && block.result ? (
        <Row marker="" style={{opacity: progress(frame, block.result.at, 6)}}>
          <span style={{color: COLOR.text2}}>⎿  </span>
          <Spans spans={block.result.spans} />
        </Row>
      ) : null}
    </div>
  );
};

export const Terminal: React.FC<{header: TerminalHeader; blocks: TerminalBlock[]; scroll?: number}> = ({header, blocks, scroll = 0}) => {
  const frame = useCurrentFrame();
  const prompt = blocks.filter((b): b is Extract<TerminalBlock, {kind: 'prompt'}> => b.kind === 'prompt').find((b) => frame >= b.at && frame < b.submit);
  const spinner = blocks.filter((b): b is Extract<TerminalBlock, {kind: 'spinner'}> => b.kind === 'spinner').find((b) => frame >= b.at && frame < b.until);
  const visible = blocks.filter((b) => (b.kind === 'prompt' ? frame >= b.submit : b.kind !== 'spinner' && frame >= b.at));
  const typing = prompt ? typed(prompt.text, frame, prompt.at, prompt.cps ?? 32) : '';
  const settled = prompt ? typing.length === prompt.text.length : true;
  return (
    <AbsoluteFill style={{background: COLOR.bg}}>
      <div
        style={{
          position: 'absolute',
          left: 100,
          top: 64,
          width: 1080,
          height: 592,
          borderRadius: 12,
          background: COLOR.surface,
          boxShadow: `0 0 0 1px ${COLOR.border}, 0 30px 80px rgba(0, 0, 0, 0.55)`,
          overflow: 'hidden',
          fontFamily: MONO,
          fontSize: FONT,
          lineHeight: LINE,
          color: COLOR.text,
        }}
      >
        <div style={{position: 'relative', height: 36, borderBottom: `1px solid ${COLOR.border}`}}>
          <div style={{position: 'absolute', left: 14, top: 12, display: 'flex', gap: 8}}>
            {['#ff5f57', '#febc2e', '#28c840'].map((c) => (
              <div key={c} style={{width: 12, height: 12, borderRadius: 6, background: c}} />
            ))}
          </div>
          <div style={{textAlign: 'center', fontFamily: SANS, fontSize: 14, lineHeight: '36px', color: COLOR.windowTitle}}>{header.title}</div>
        </div>
        <div style={{position: 'absolute', left: 30, right: 30, top: 36 + 22 - scroll}}>
          <div style={{display: 'flex', gap: 22, alignItems: 'center', marginBottom: 18}}>
            <Mascot cell={FONT * 1.25} color={COLOR.claude} />
            <div style={{lineHeight: 1.3}}>
              <div style={{fontWeight: 700}}>Claude Code</div>
              <div style={{color: COLOR.text2}}>{header.model}</div>
              <div style={{color: COLOR.text2}}>{header.cwd}</div>
            </div>
          </div>
          <div style={{display: 'grid', gap: 14}}>
            {visible.map((block, i) => {
              if (block.kind === 'prompt') {
                return (
                  <div key={i} style={{background: COLOR.border, padding: '2px 10px', margin: '0 -10px'}}>
                    <Row marker={<span style={{color: COLOR.text2}}>&gt;</span>}>{block.text}</Row>
                  </div>
                );
              }
              if (block.kind === 'text') {
                return (
                  <Row key={i} marker="●" style={{opacity: progress(frame, block.at, 6)}}>
                    <Spans spans={block.spans} />
                  </Row>
                );
              }
              if (block.kind === 'tool') {
                return <ToolCall key={i} block={block} frame={frame} />;
              }
              return null;
            })}
            {spinner ? (
              <Row marker={<span style={{color: COLOR.claude}}>{SPINNER[Math.floor(frame / 3) % SPINNER.length]}</span>}>
                <span style={{color: COLOR.claude}}>{spinner.word}</span>
                <span style={{color: COLOR.text2}}>
                  {' '}
                  (
                  {spinner.elapsed
                    ? `${formatElapsed(spinner.elapsed[0] + ((frame - spinner.at) / Math.max(1, spinner.until - spinner.at)) * (spinner.elapsed[1] - spinner.elapsed[0]))} · `
                    : ''}
                  esc to interrupt)
                </span>
              </Row>
            ) : null}
          </div>
          <div style={{marginTop: 18, borderTop: `1px solid ${COLOR.border}`, borderBottom: `1px solid ${COLOR.border}`, padding: '6px 0'}}>
            <Row marker={<span style={{color: COLOR.text2}}>&gt;</span>}>
              {typing}
              <Caret frame={frame} solid={!settled} />
            </Row>
          </div>
          <div style={{color: COLOR.text2, marginTop: 6, paddingLeft: '1.6em'}}>? for shortcuts</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
