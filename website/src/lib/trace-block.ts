export interface TraceMessage {
  direction: "out" | "in";
  text: string;
}

const ARROWS: Record<string, TraceMessage["direction"]> = { "→": "out", "←": "in" };

export function isTraceBlock(text: string): boolean {
  const lines = text.split("\n").filter((line) => line.trim());
  return lines.length > 0 && lines[0][0] in ARROWS;
}

export function parseTraceBlock(text: string): TraceMessage[] {
  const messages: TraceMessage[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const direction = ARROWS[line[0]];
    if (direction) messages.push({ direction, text: line.slice(1).trim() });
    else if (messages.length) messages[messages.length - 1].text += `\n${line}`;
  }
  return messages;
}

export function traceJson(text: string): unknown[] {
  return parseTraceBlock(text).map((message) => JSON.parse(message.text));
}
