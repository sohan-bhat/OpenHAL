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
  { key: "blocked", label: "Blocked", text: "A command that breaks a limit or an interlock ends here, with an error from the registry." },
  { key: "driver", label: "Driver", text: "Acts only with a single-use Grant for that one command." },
  { key: "device", label: "Device", text: "Applies the command and reports the new value back." },
];

const KEYS: Record<string, string> = { "hub.files": "files" };

function decodeEntities(text: string): string {
  return text.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#39;/g, "'").replace(/&amp;/g, "&");
}

export function diagramLabels(svg: string): Map<string, string> {
  const labels = new Map<string, string>();
  for (const match of svg.matchAll(/<g class="([A-Za-z0-9+/=]+)(?: node)?">/g)) {
    const encoded = match[1];
    const body = svg.slice(match.index ?? 0);
    let name: string;
    try {
      name = Buffer.from(encoded, "base64").toString("utf8");
    } catch {
      continue;
    }
    const key = KEYS[name] ?? name;
    if (!FLOW_NODES.some((node) => node.key === key) || labels.has(key)) continue;
    const text = /<text[^>]*>([\s\S]*?)<\/text>/.exec(body)?.[1];
    if (!text) continue;
    const parts = [...text.matchAll(/<tspan[^>]*>([\s\S]*?)<\/tspan>/g)].map((part) => part[1]);
    labels.set(key, decodeEntities((parts.length ? parts.join(" ") : text).replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim());
  }
  return labels;
}

export function flowNodes(svg: string | null): FlowNode[] {
  const labels = svg ? diagramLabels(svg) : new Map<string, string>();
  return FLOW_NODES.map((node) => ({ ...node, label: labels.get(node.key) ?? node.label }));
}

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
