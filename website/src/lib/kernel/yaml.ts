/**
 * Parse device file YAML with the same restrictions as openhal/spec/loader.py. One document,
 * no anchors, aliases or custom tags, at most 256 KiB, YAML 1.2 booleans. Integers come back as
 * bigint so the limits hash can tell 100 from 100.0, as Python does.
 */

import { isAlias, isNode, parseDocument, visit } from "yaml";

export const MAX_FILE_BYTES = 256 * 1024;

export class YamlError extends Error {
  constructor(
    message: string,
    public line: number | null = null,
  ) {
    super(message);
  }
}

export function parseDeviceYaml(text: string): unknown {
  if (new TextEncoder().encode(text).length > MAX_FILE_BYTES) {
    throw new YamlError(`The file is larger than ${MAX_FILE_BYTES / 1024} KiB.`);
  }
  const doc = parseDocument(text, { version: "1.2", schema: "core", intAsBigInt: true, uniqueKeys: true, prettyErrors: false });
  if (doc.errors.length) {
    const first = doc.errors[0];
    throw new YamlError(first.message.split("\n")[0], first.linePos?.[0]?.line ?? null);
  }
  let problem: YamlError | null = null;
  const lineOf = (offset: number | undefined) => (offset === undefined ? null : text.slice(0, offset).split("\n").length);
  visit(doc, (_key, node) => {
    if (problem) return visit.BREAK;
    if (isAlias(node)) {
      problem = new YamlError("YAML aliases are not allowed in device files.", lineOf(node.range?.[0]));
    } else if (isNode(node)) {
      if (node.anchor) problem = new YamlError("YAML anchors are not allowed in device files.", lineOf(node.range?.[0]));
      else if (node.tag && !node.tag.startsWith("tag:yaml.org,2002:")) {
        problem = new YamlError(`Custom YAML tags such as ${node.tag} are not allowed.`, lineOf(node.range?.[0]));
      }
    }
    return undefined;
  });
  if (problem) throw problem;
  return doc.toJS({ maxAliasCount: 0 });
}
