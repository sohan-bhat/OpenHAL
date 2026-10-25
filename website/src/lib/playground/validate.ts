// Live validation for the playground. YAML parsing with the loader's restrictions, the JSON Schema
// from spec/schema (imported at build time, never copied), then the model checks the schema can't
// express, such as units, min below max and interlock expressions.

import type { ErrorObject } from "ajv";
import validateSchema from "virtual:device-schema-validator";
import { DeviceFileError, expandShorthand, loadDeviceFile, type DeviceFile } from "../kernel/model";
import { YamlError, parseDeviceYaml } from "../kernel/yaml";

export interface Problem {
  source: "yaml" | "schema" | "spec";
  where: string;
  message: string;
  line: number | null;
}

export interface Checked {
  raw: unknown;
  file: DeviceFile | null;
  problems: Problem[];
}

function plainNumbers(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (Array.isArray(value)) return value.map(plainNumbers);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, plainNumbers(item)]));
  }
  return value;
}

function place(error: ErrorObject): string {
  const parts = error.instancePath.split("/").filter(Boolean);
  let text = "";
  for (const part of parts) text += /^\d+$/.test(part) ? `[${part}]` : text ? `.${part}` : part;
  return text || "file";
}

function message(error: ErrorObject): string {
  switch (error.keyword) {
    case "additionalProperties":
      return `Unknown key ${(error.params as { additionalProperty: string }).additionalProperty}.`;
    case "required":
      return `Missing ${(error.params as { missingProperty: string }).missingProperty}.`;
    case "enum":
      return `Must be one of ${(error.params as { allowedValues: unknown[] }).allowedValues.join(", ")}.`;
    case "pattern":
      return `Doesn't match ${(error.params as { pattern: string }).pattern}.`;
    default: {
      const text = error.message ?? "is not valid";
      return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
    }
  }
}

/** Schema errors, keeping the most specific one per place so anyOf branches don't repeat. */
function schemaProblems(errors: ErrorObject[]): Problem[] {
  const useful = errors.filter((error) => error.keyword !== "anyOf" && error.keyword !== "if");
  const seen = new Set<string>();
  const out: Problem[] = [];
  for (const error of useful) {
    const where = place(error);
    const text = message(error);
    const key = `${where}|${text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ source: "schema", where, message: text, line: null });
  }
  return out.slice(0, 12);
}

function lineOf(text: string, where: string): number | null {
  const key = where.split(/[.[]/).filter(Boolean).pop();
  if (!key || /^\d+\]?$/.test(key)) return null;
  const index = text.split("\n").findIndex((line) => new RegExp(`^\\s*${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*:`).test(line));
  return index === -1 ? null : index + 1;
}

export function deviceProblems(text: string): Checked {
  let raw: unknown;
  try {
    raw = parseDeviceYaml(text);
  } catch (error) {
    if (error instanceof YamlError) return { raw: null, file: null, problems: [{ source: "yaml", where: "file", message: error.message, line: error.line }] };
    throw error;
  }
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    return { raw, file: null, problems: [{ source: "yaml", where: "file", message: "A device file must be a mapping at the top level.", line: 1 }] };
  }
  const expanded = plainNumbers(expandShorthand(raw));
  if (!validateSchema(expanded)) {
    const problems = schemaProblems(validateSchema.errors ?? []).map((problem) => ({ ...problem, line: lineOf(text, problem.where) }));
    return { raw, file: null, problems };
  }
  try {
    return { raw, file: loadDeviceFile(raw), problems: [] };
  } catch (error) {
    if (!(error instanceof DeviceFileError)) throw error;
    return {
      raw,
      file: null,
      problems: error.problems.map((problem) => {
        const index = problem.indexOf(": ");
        const where = index === -1 ? "file" : problem.slice(0, index);
        return { source: "spec" as const, where, message: index === -1 ? problem : problem.slice(index + 2), line: lineOf(text, where) };
      }),
    };
  }
}
