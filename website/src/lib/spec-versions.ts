import changelog from "../../../spec/CHANGELOG.md?raw";
import { SPEC_VERSION } from "../config/brand";

export interface SpecVersion {
  version: string;
  status: string;
  date: string;
  current: boolean;
}

export function parseVersions(text: string): SpecVersion[] {
  const versions: SpecVersion[] = [];
  for (const match of text.matchAll(/^## (\d+\.\d+(?:\.\d+)?)\s*\(([^)]*)\)/gm)) {
    const parts = match[2].split(",").map((part) => part.trim());
    const date = parts.find((part) => /^\d{4}-\d{2}-\d{2}$/.test(part)) ?? "";
    const status = parts.filter((part) => part !== date).join(", ") || "released";
    versions.push({ version: match[1], status, date, current: match[1] === SPEC_VERSION });
  }
  return versions;
}

export function specVersions(): SpecVersion[] {
  return parseVersions(changelog);
}
