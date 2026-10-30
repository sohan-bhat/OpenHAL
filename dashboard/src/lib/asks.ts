import { principalInfo } from "./trace";
import type { ConfirmationRequest, DeviceView } from "./types";
import { formatQuantity, formatValue } from "./units";

export interface Ask {
  actor: string;
  name: string;
  verb: "run" | "set";
  target: string;
  value: string | null;
  device: string;
  does: string | null;
  limit: string | null;
  why: string;
  file: string | null;
}

const ACTORS: Record<string, string> = { agent: "The agent", routine: "The routine", human: "The person", system: "The hub" };

export function fileName(path: string | null | undefined): string | null {
  return path ? (path.split("/").pop() ?? null) : null;
}

export function askOf(request: ConfirmationRequest, view: DeviceView | undefined): Ask {
  const who = principalInfo(request.requested_by);
  const command = request.command;
  const isAction = command.kind === "action";
  const target = (isAction ? command.action : command.channel) ?? "";
  const file = fileName(view?.path);
  let value: string | null = null;
  if (isAction) {
    value = command.args && Object.keys(command.args).length ? formatValue(command.args) : null;
  } else if (command.value !== undefined) {
    value = formatQuantity(command.value, command.unit ?? view?.write[target]?.unit ?? null);
  }
  const action = isAction ? view?.actions[target] : undefined;
  const channel = !isAction ? view?.write[target] : undefined;
  const tier = action?.confirm ?? channel?.confirm ?? null;
  let limit: string | null = null;
  if (channel && channel.min !== null && channel.max !== null) {
    limit = `${formatQuantity(channel.min, channel.unit)} to ${formatQuantity(channel.max, channel.unit)}`;
  }
  const source = file ?? "The Device File";
  let why: string;
  if (view?.hazard === "high") why = `${view.name} has a high hazard, so a person confirms every command.`;
  else if (tier === "confirm-each-time") why = `${source} requires a person to confirm ${target} each time.`;
  else if (tier === "confirm") why = `${source} requires a person to confirm ${target}.`;
  else why = request.dry_run.message;
  return {
    actor: ACTORS[who.kind] ?? "",
    name: who.name || who.label,
    verb: isAction ? "run" : "set",
    target,
    value,
    device: view?.name ?? command.device,
    does: action?.description ?? null,
    limit,
    why: `${why} Nothing reaches the device until you approve.`,
    file,
  };
}

export function askedAgo(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  if (whole < 60) return `${whole} s ago`;
  return `${Math.floor(whole / 60)} min ago`;
}
