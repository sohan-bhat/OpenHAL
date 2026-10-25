import { DeviceFileError, UnitError, deviceId, effectiveHazard, loadDeviceFile, unconfirmed, type DeviceFile } from "./kernel";
import { YamlError, parseDeviceYaml } from "./kernel/yaml";

export type Verification = "unverified" | "tested-reads" | "verified-on-hardware";

export interface LibraryEntry {
  slug: string;
  path: string;
  title: string;
  manufacturer: string | null;
  model: string | null;
  deviceId: string;
  driver: string;
  hazard: string;
  verification: Verification;
  report: string | null;
  source: string;
  confirmed: boolean;
  suggested: string[];
  unconfirmed: string[];
  reads: number;
  writes: number;
  actions: number;
  match: string[];
  text: string;
  file: DeviceFile | null;
  problems: string[];
}

function verificationOf(file: DeviceFile): { status: Verification; report: string | null } {
  const provenance = file.provenance as { verification?: { status?: string; report?: string } };
  const status = provenance.verification?.status;
  const value: Verification = status === "tested-reads" || status === "verified-on-hardware" ? status : "unverified";
  return { status: value, report: provenance.verification?.report ?? null };
}

function matchList(file: DeviceFile): string[] {
  const out: string[] = [];
  for (const [key, value] of Object.entries(file.match)) {
    if (Array.isArray(value)) value.forEach((item) => out.push(`${key} ${String(item)}`));
    else if (value && typeof value === "object") Object.entries(value).forEach(([k, v]) => out.push(`${key}.${k} ${String(v)}`));
    else if (value !== null && value !== undefined) out.push(`${key} ${String(value)}`);
  }
  return out;
}

function suggestedEntries(file: DeviceFile): string[] {
  return [
    ...Object.entries(file.write).filter(([, spec]) => spec.suggested).map(([name]) => name),
    ...Object.entries(file.actions).filter(([, spec]) => spec.suggested).map(([name]) => `${name} (action)`),
  ];
}

function isConfirmed(file: DeviceFile): boolean {
  if (unconfirmed(file).length > 0) return false;
  return file.confirmed !== null || Object.keys(file.write).length + Object.keys(file.actions).length > 0;
}

export function parseLibrary(files: Record<string, string>): LibraryEntry[] {
  const entries: LibraryEntry[] = [];
  for (const [path, text] of Object.entries(files)) {
    const slug = path.replace(/^.*?library\//, "").replace(/\.hal\.yaml$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    let file: DeviceFile | null = null;
    let problems: string[] = [];
    try {
      file = loadDeviceFile(parseDeviceYaml(text));
    } catch (error) {
      if (error instanceof DeviceFileError) problems = error.problems;
      else if (error instanceof YamlError || error instanceof UnitError) problems = [error.message];
      else throw error;
    }
    if (!file) {
      entries.push({
        slug, path, title: slug, manufacturer: null, model: null, deviceId: slug, driver: "", hazard: "", verification: "unverified",
        report: null, source: "", confirmed: false, suggested: [], unconfirmed: [], reads: 0, writes: 0, actions: 0, match: [], text, file: null, problems,
      });
      continue;
    }
    const verification = verificationOf(file);
    const provenance = file.provenance as { source?: string };
    entries.push({
      slug,
      path,
      title: file.device.model ? `${file.device.manufacturer ? `${file.device.manufacturer} ` : ""}${file.device.model}` : file.device.name,
      manufacturer: file.device.manufacturer,
      model: file.device.model,
      deviceId: deviceId(file),
      driver: file.connect.driver,
      hazard: effectiveHazard(file),
      verification: verification.status,
      report: verification.report,
      source: provenance.source ?? "hand-written",
      confirmed: isConfirmed(file),
      suggested: suggestedEntries(file),
      unconfirmed: unconfirmed(file),
      reads: Object.keys(file.read).length,
      writes: Object.keys(file.write).length,
      actions: Object.keys(file.actions).length,
      match: matchList(file),
      text,
      file,
      problems,
    });
  }
  return entries.sort((a, b) => a.title.localeCompare(b.title));
}

const files = import.meta.glob<string>("../../../library/**/*.hal.yaml", { query: "?raw", import: "default", eager: true });

export function libraryEntries(): LibraryEntry[] {
  return parseLibrary(Object.fromEntries(Object.entries(files).map(([path, text]) => [path.replace(/^(\.\.\/)+/, ""), text])));
}
