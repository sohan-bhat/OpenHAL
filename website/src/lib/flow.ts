import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface FlowNode {
  key: string;
  label: string;
  text: string;
}

export const FLOW_NODES: FlowNode[] = [
  { key: "client", label: "AI client", text: "Sends hal/write over JSON-RPC, through MCP or a direct connection." },
  { key: "files", label: "Device files", text: "Hold each device's channels and the limits a person confirmed." },
  { key: "hub", label: "OpenHAL hub", text: "Owns every device and routes each request to the kernel." },
  { key: "kernel", label: "Safety kernel", text: "Checks units, range, rate, interlocks and confirmation before anything moves." },
  { key: "blocked", label: "Blocked", text: "A request outside the limits ends here as error -32010 LIMIT_EXCEEDED." },
  { key: "driver", label: "Driver", text: "Acts only with the kernel's single-use grant for that one command." },
  { key: "device", label: "Device", text: "Applies the command and reports the new value back." },
];

export interface FlowSvg {
  light: string;
  dark: string;
  width: number;
  height: number;
}

function size(svg: string): { width: number; height: number } {
  const box = /viewBox="[\d.\s-]*?\s([\d.]+)\s([\d.]+)"/.exec(svg);
  if (box) return { width: Number(box[1]), height: Number(box[2]) };
  const width = Number(/\swidth="([\d.]+)"/.exec(svg)?.[1] ?? 0);
  const height = Number(/\sheight="([\d.]+)"/.exec(svg)?.[1] ?? 0);
  return { width, height };
}

function clean(svg: string, prefix: string): string {
  const body = svg.replace(/<\?xml[^>]*>/, "").replace(/<!DOCTYPE[^>]*>/i, "").trim();
  return body.replace(/\sid="([^"]+)"/g, ` id="${prefix}-$1"`).replace(/url\(#([^)]+)\)/g, `url(#${prefix}-$1)`).replace(/href="#([^"]+)"/g, `href="#${prefix}-$1"`);
}

export function readFlow(root = join(process.cwd(), "..")): FlowSvg | null {
  const light = join(root, "docs", "diagrams", "flow-light.svg");
  const dark = join(root, "docs", "diagrams", "flow-dark.svg");
  if (!existsSync(light) || !existsSync(dark)) return null;
  const lightText = readFileSync(light, "utf8");
  return { light: clean(lightText, "flow-l"), dark: clean(readFileSync(dark, "utf8"), "flow-d"), ...size(lightText) };
}
