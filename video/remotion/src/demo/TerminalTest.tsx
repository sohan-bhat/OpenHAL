import {Terminal} from './Terminal';

export const TerminalTest: React.FC = () => (
  <Terminal
    header={{title: 'Claude Code', model: 'Opus 5.5 · Claude Max', cwd: '~/desk'}}
    blocks={[
      {kind: 'prompt', text: 'Pick up the red cube and put it in the bin.', at: 6, submit: 60},
      {kind: 'spinner', word: 'Thinking…', at: 62, until: 90, elapsed: [0, 4]},
      {kind: 'text', text: 'I’ll read where the cube is, then move the arm above it.', at: 90},
      {
        kind: 'tool',
        server: 'openhal',
        tool: 'action',
        args: 'device: "arm", action: "move_to", args: {"x": {"value": 200, "unit": "mm"}, "y": {"value": 90, "unit": "mm"}, "z": {"value": 60, "unit": "mm"}}',
        at: 100,
        brand: true,
        result: {spans: [{text: 'done', tone: 'ok', bold: true}, {text: '  Done. move_to ran.', tone: 'muted'}], at: 125},
      },
    ]}
  />
);
