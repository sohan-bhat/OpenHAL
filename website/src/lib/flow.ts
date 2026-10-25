import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface FlowNode {
  key: string;
  label: string;
  text: string;
}

export const FLOW_NODES: FlowNode[] = [
  { key: "client", label: "AI client", text: "Sends requests over JSON-RPC, directly or through MCP." },
  { key: "hub", label: "OpenHAL hub", text: "Owns every device and passes each request to the Safety Kernel." },
  { key: "files", label: "Device files", text: "Hold each device's channels and the limits a person confirmed." },
  { key: "kernel", label: "Safety kernel", text: "Checks units, range, rate, interlocks and confirmation, in that order." },
  { key: "blocked", label: "Blocked", text: "A request outside the limits ends here as error -32010 LIMIT_EXCEEDED." },
  { key: "driver", label: "Driver", text: "Acts only with a single-use Grant for that one command." },
  { key: "device", label: "Device", text: "Applies the command and reports the new value back." },
];

export const FLOW_DEFAULT = "Every command passes the Safety Kernel before a Driver may act.";

export interface FlowArt {
  light: string;
  dark: string;
  lightFlows: string;
  darkFlows: string;
  width: number;
  height: number;
}

export interface FlowSvg {
  wide: FlowArt;
  narrow: FlowArt | null;
}

function size(svg: string): { width: number; height: number } {
  const width = Number(/<svg[^>]*\swidth="([\d.]+)"/.exec(svg)?.[1] ?? 0);
  const height = Number(/<svg[^>]*\sheight="([\d.]+)"/.exec(svg)?.[1] ?? 0);
  if (width && height) return { width, height };
  const box = /viewBox="[\d.\s-]*?\s([\d.]+)\s([\d.]+)"/.exec(svg);
  return { width: Number(box?.[1] ?? 0), height: Number(box?.[2] ?? 0) };
}

function clean(svg: string, prefix: string): string {
  const body = svg.replace(/<\?xml[^>]*>/, "").replace(/<!DOCTYPE[^>]*>/i, "").trim();
  return body
    .replace(/\sid="([^"]+)"/g, ` id="${prefix}-$1"`)
    .replace(/url\(#([^)]+)\)/g, `url(#${prefix}-$1)`)
    .replace(/href="#([^"]+)"/g, `href="#${prefix}-$1"`)
    .replace(/aria-labelledby="([^"]+)"/g, (_, ids: string) => `aria-labelledby="${ids.split(/\s+/).map((id) => `${prefix}-${id}`).join(" ")}"`);
}

function splitFlows(svg: string): [string, string] {
  const start = svg.indexOf('<g class="oh-flows"');
  const box = /<svg[^>]*class="[^"]*d2-svg[^"]*"[^>]*viewBox="([^"]+)"/.exec(svg)?.[1];
  if (start === -1 || !box) return [svg, ""];
  const end = svg.indexOf("</g>", start) + "</g>".length;
  const overlay = `<svg class="flow-overlay" viewBox="${box}" preserveAspectRatio="xMinYMin meet" aria-hidden="true" focusable="false">${svg.slice(start, end)}</svg>`;
  return [svg.slice(0, start) + svg.slice(end), overlay];
}

function pair(root: string, name: string, prefix: string): FlowArt | null {
  const light = join(root, "docs", "diagrams", `${name}-light.svg`);
  const dark = join(root, "docs", "diagrams", `${name}-dark.svg`);
  if (!existsSync(light) || !existsSync(dark)) return null;
  const lightText = readFileSync(light, "utf8");
  const [lightArt, lightFlows] = splitFlows(clean(lightText, `${prefix}l`));
  const [darkArt, darkFlows] = splitFlows(clean(readFileSync(dark, "utf8"), `${prefix}d`));
  return { light: lightArt, dark: darkArt, lightFlows, darkFlows, ...size(lightText) };
}

export function readFlow(root = join(process.cwd(), "..")): FlowSvg | null {
  const wide = pair(root, "flow", "fw");
  if (!wide) return null;
  return { wide, narrow: pair(root, "flow-narrow", "fn") };
}
