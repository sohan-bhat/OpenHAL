import type {Stat, Device} from './Cards';
import type {CameraMove} from './DeskScene';
import type {CursorKey} from './Cursor';
import type {HubFacts, PendingRequest, DeviceSummary} from './Inspector';
import type {TerminalBlock, TerminalHeader} from './Terminal';
import type {Quat, Vec3, ArmPose} from './recording';

export type Tone = 'ok' | 'blocked' | 'pending' | 'text';

export type PanelSpec = {
  title: string;
  subtitle: string;
  label: string;
  unit: string;
  limit: number;
  scaleMax: number;
  limitLabel: string;
  value: 'speed' | number;
  countFrom?: number;
  countFrames?: number;
  verdict?: {text: string; tone: Tone; at: number} | null;
};

export type TerminalScene = {id: string; kind: 'terminal'; from: number; frames: number; blocks: TerminalBlock[]};

export type DeskSceneSpec = {
  id: string;
  kind: 'desk';
  from: number;
  frames: number;
  poses: number[][];
  speeds: number[];
  camera: CameraMove;
  shots?: {start: number; camera: CameraMove}[];
  panel: PanelSpec;
  stop?: {hub: HubFacts; reason: string; press: number; cursor: CursorKey[]};
};

export type InspectorScene = {
  id: string;
  kind: 'inspector';
  from: number;
  frames: number;
  hub: HubFacts;
  device: DeviceSummary;
  request: PendingRequest;
  cursor: CursorKey[];
  press: number;
  zoom: {from: number; to: number; origin: [number, number]};
};

export type StatsScene = {id: string; kind: 'stats'; from: number; frames: number; stats: Stat[]; source: string};
export type DevicesScene = {id: string; kind: 'devices'; from: number; frames: number; title: string; devices: Device[]};
export type EndScene = {id: string; kind: 'end'; from: number; frames: number; tagline: string; command: string; url: string; finePrint: string};

export type Scene = TerminalScene | DeskSceneSpec | InspectorScene | StatsScene | DevicesScene | EndScene;

export type Edit = {take: string; fps: number; frames: number; header: TerminalHeader; scenes: Scene[]};

export const poseOf = (row: number[]): ArmPose => ({
  joints: {shoulder_pan: row[0], shoulder_lift: row[1], elbow_flex: row[2], wrist_flex: row[3], wrist_roll: row[4]},
  jaw: row[5],
  cube: {position: [row[6], row[7], row[8]] as Vec3, quaternion: [row[9], row[10], row[11], row[12]] as Quat},
});
