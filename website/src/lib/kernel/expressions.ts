import { formatG, isClose, pyFloatRepr, pyStrRepr } from "./pyformat";
import { UnitError, convert, parseQuantity, parseUnit } from "./units";

export const MAX_LENGTH = 256;
export const MAX_DEPTH = 16;
const KEYWORDS = new Set(["and", "or", "not", "true", "false"]);

export type Tri = boolean | null;

export class ExpressionError extends Error {}

export interface Ref {
  kind: "ref";
  device: string | null;
  name: string;
}
export interface Lit {
  kind: "lit";
  value: number | boolean | string;
  unit: string | null;
  quoted: boolean;
}
export interface Compare {
  kind: "compare";
  op: string;
  left: Node;
  right: Node;
}
export interface Not {
  kind: "not";
  operand: Node;
}
export interface And {
  kind: "and";
  operands: Node[];
}
export interface Or {
  kind: "or";
  operands: Node[];
}
export type Node = Ref | Lit | Compare | Not | And | Or;

export interface Value {
  value: number | boolean | string;
  unit: string | null;
}

export type Resolver = (ref: Ref) => Value | null;

export function refText(ref: Ref): string {
  return ref.device ? `${ref.device}.${ref.name}` : ref.name;
}

const TOKEN =
  /(?<space>\s+)|(?<op>==|!=|<=|>=|<|>)|(?<lparen>\()|(?<rparen>\))|(?<string>'[^']{0,120}'|"[^"]{0,120}")|(?<number>[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)|(?<name>[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)/y;
const UNIT = /\s*([A-Za-z%°µ][A-Za-z0-9%°µ/*^_]*(?:\s*\/\s*[A-Za-z]+)?)/y;

interface Tok {
  kind: string;
  text: string;
  unit: string | null;
}

function tokenize(text: string): Tok[] {
  const tokens: Tok[] = [];
  let pos = 0;
  while (pos < text.length) {
    TOKEN.lastIndex = pos;
    const match = TOKEN.exec(text);
    if (!match || match.index + match[0].length === pos) {
      throw new ExpressionError(`Unexpected character ${pyStrRepr(text[pos])} at position ${pos}.`);
    }
    const groups = match.groups ?? {};
    const kind = Object.keys(groups).find((key) => groups[key] !== undefined) ?? "";
    pos = TOKEN.lastIndex;
    if (kind === "space") continue;
    if (kind === "number") {
      UNIT.lastIndex = pos;
      const unitMatch = UNIT.exec(text);
      let unit: string | null = null;
      if (unitMatch && !KEYWORDS.has(unitMatch[1].toLowerCase())) {
        unit = unitMatch[1].trim();
        pos = UNIT.lastIndex;
      }
      tokens.push({ kind: "number", text: match[0], unit });
      continue;
    }
    tokens.push({ kind, text: match[0], unit: null });
  }
  return tokens;
}

class Parser {
  pos = 0;
  constructor(
    private tokens: Tok[],
    private channels: Set<string> | null,
  ) {}

  peek(): Tok | undefined {
    return this.tokens[this.pos];
  }

  take(): Tok {
    const tok = this.peek();
    if (tok === undefined) throw new ExpressionError("The expression ends too early.");
    this.pos += 1;
    return tok;
  }

  keyword(word: string): boolean {
    const tok = this.peek();
    if (tok !== undefined && tok.kind === "name" && tok.text.toLowerCase() === word) {
      this.pos += 1;
      return true;
    }
    return false;
  }

  parse(): Node {
    const node = this.orExpr(0);
    const rest = this.peek();
    if (rest !== undefined) throw new ExpressionError(`Unexpected ${pyStrRepr(rest.text)} after a complete expression.`);
    return node;
  }

  depth(depth: number): number {
    if (depth > MAX_DEPTH) throw new ExpressionError(`Expressions may nest at most ${MAX_DEPTH} levels.`);
    return depth + 1;
  }

  orExpr(depth: number): Node {
    depth = this.depth(depth);
    const parts = [this.andExpr(depth)];
    while (this.keyword("or")) parts.push(this.andExpr(depth));
    return parts.length === 1 ? parts[0] : { kind: "or", operands: parts };
  }

  andExpr(depth: number): Node {
    depth = this.depth(depth);
    const parts = [this.notExpr(depth)];
    while (this.keyword("and")) parts.push(this.notExpr(depth));
    return parts.length === 1 ? parts[0] : { kind: "and", operands: parts };
  }

  notExpr(depth: number): Node {
    depth = this.depth(depth);
    if (this.keyword("not")) return { kind: "not", operand: this.notExpr(depth) };
    return this.compare(depth);
  }

  compare(depth: number): Node {
    const left = this.operand(depth);
    const tok = this.peek();
    if (tok !== undefined && tok.kind === "op") {
      this.pos += 1;
      return { kind: "compare", op: tok.text, left, right: this.operand(depth) };
    }
    return left;
  }

  operand(depth: number): Node {
    depth = this.depth(depth);
    const tok = this.take();
    if (tok.kind === "lparen") {
      const inner = this.orExpr(depth);
      const closing = this.take();
      if (closing.kind !== "rparen") throw new ExpressionError("A parenthesis is not closed.");
      return inner;
    }
    if (tok.kind === "number") {
      const number = Number(tok.text);
      if (!Number.isFinite(number)) throw new ExpressionError("Numbers must be finite.");
      return { kind: "lit", value: number, unit: tok.unit, quoted: false };
    }
    if (tok.kind === "string") return { kind: "lit", value: tok.text.slice(1, -1), unit: null, quoted: true };
    if (tok.kind === "name") {
      const lowered = tok.text.toLowerCase();
      if (lowered === "true" || lowered === "false") return { kind: "lit", value: lowered === "true", unit: null, quoted: false };
      if (KEYWORDS.has(lowered)) throw new ExpressionError(`Unexpected keyword ${pyStrRepr(tok.text)}.`);
      if (tok.text.includes(".")) {
        const index = tok.text.indexOf(".");
        return { kind: "ref", device: tok.text.slice(0, index), name: tok.text.slice(index + 1) };
      }
      if (this.channels === null || this.channels.has(tok.text)) return { kind: "ref", device: null, name: tok.text };
      return { kind: "lit", value: tok.text, unit: null, quoted: false };
    }
    throw new ExpressionError(`Unexpected ${pyStrRepr(tok.text)}.`);
  }
}

export function parse(text: string, channels: Iterable<string> | null = null): Node {
  if (typeof text !== "string" || !text.trim()) throw new ExpressionError("An expression can't be empty.");
  if (text.length > MAX_LENGTH) throw new ExpressionError(`Expressions may be at most ${MAX_LENGTH} characters.`);
  return new Parser(tokenize(text), channels === null ? null : new Set(channels)).parse();
}

const cache = new Map<string, Node>();

export function parseCached(text: string, channels: Iterable<string>): Node {
  const sorted = [...channels].sort();
  const key = `${text}\u0000${sorted.join(",")}`;
  let node = cache.get(key);
  if (!node) {
    node = parse(text, sorted);
    if (cache.size > 4096) cache.clear();
    cache.set(key, node);
  }
  return node;
}

export function words(node: Node): Array<[string, Node | null]> {
  if (node.kind === "lit") return typeof node.value === "string" && !node.quoted ? [[node.value, null]] : [];
  if (node.kind === "ref") return [];
  if (node.kind === "compare") {
    const found: Array<[string, Node | null]> = [];
    for (const [side, other] of [
      [node.left, node.right],
      [node.right, node.left],
    ] as const) {
      if (side.kind === "lit" && typeof side.value === "string" && !side.quoted) found.push([side.value, other]);
    }
    return found;
  }
  if (node.kind === "not") return words(node.operand);
  return node.operands.flatMap(words);
}

export function references(node: Node): Ref[] {
  const seen = new Map<string, Ref>();
  const walk = (current: Node) => {
    if (current.kind === "ref") seen.set(`${current.device ?? ""}.${current.name}`, current);
    else if (current.kind === "compare") {
      walk(current.left);
      walk(current.right);
    } else if (current.kind === "not") walk(current.operand);
    else if (current.kind === "and" || current.kind === "or") current.operands.forEach(walk);
  };
  walk(node);
  return [...seen.values()];
}

function resolve(node: Node, resolver: Resolver): Value | null {
  if (node.kind === "ref") return resolver(node);
  if (node.kind === "lit") return { value: node.value, unit: node.unit };
  throw new ExpressionError("Comparisons take channels and values, not other comparisons.");
}

function compareNumbers(op: string, left: number, right: number): boolean {
  const close = isClose(left, right, 1e-9, 1e-12);
  switch (op) {
    case "==":
      return close;
    case "!=":
      return !close;
    case "<":
      return left < right && !close;
    case "<=":
      return left < right || close;
    case ">":
      return left > right && !close;
    default:
      return left > right || close;
  }
}

function evaluateCompare(node: Compare, resolver: Resolver): Tri {
  const left = resolve(node.left, resolver);
  const right = resolve(node.right, resolver);
  if (left === null || right === null) return null;
  if (typeof left.value === "boolean" || typeof right.value === "boolean") {
    if (node.op !== "==" && node.op !== "!=") return null;
    const same = left.value === right.value && typeof left.value === typeof right.value;
    return node.op === "==" ? same : !same;
  }
  if (typeof left.value === "string" || typeof right.value === "string") {
    if (node.op !== "==" && node.op !== "!=") return null;
    const text = (v: number | string) => (typeof v === "number" ? pyFloatRepr(v) : v);
    const same = text(left.value) === text(right.value);
    return node.op === "==" ? same : !same;
  }
  let rightInLeft: number;
  try {
    if (left.unit === null && right.unit === null) return compareNumbers(node.op, left.value, right.value);
    if (left.unit === null || right.unit === null) return null;
    rightInLeft = convert(parseQuantity(`${pyFloatRepr(right.value)} ${right.unit}`), left.unit);
  } catch (error) {
    if (error instanceof UnitError) return null;
    throw error;
  }
  return compareNumbers(node.op, left.value, rightInLeft);
}

export function evaluate(node: Node, resolver: Resolver): Tri {
  if (node.kind === "compare") return evaluateCompare(node, resolver);
  if (node.kind === "ref") {
    const found = resolver(node);
    return found !== null && typeof found.value === "boolean" ? found.value : null;
  }
  if (node.kind === "lit") return typeof node.value === "boolean" ? node.value : null;
  if (node.kind === "not") {
    const inner = evaluate(node.operand, resolver);
    return inner === null ? null : !inner;
  }
  const results = node.operands.map((part) => evaluate(part, resolver));
  if (node.kind === "and") {
    if (results.some((result) => result === false)) return false;
    return results.some((result) => result === null) ? null : true;
  }
  if (results.some((result) => result === true)) return true;
  return results.some((result) => result === null) ? null : false;
}

export function checkUnits(node: Node, unitOf: (ref: Ref) => string | null): void {
  if (node.kind === "compare") {
    for (const [side, other] of [
      [node.left, node.right],
      [node.right, node.left],
    ] as const) {
      if (side.kind !== "ref" || other.kind !== "lit") continue;
      const unit = unitOf(side);
      if (unit === null || typeof other.value === "boolean" || typeof other.value === "string") continue;
      if (other.unit === null) {
        throw new ExpressionError(`${formatG(other.value)} is compared with ${refText(side)}, so it needs a unit (${unit}).`);
      }
      try {
        convert(parseQuantity(`${pyFloatRepr(other.value)} ${other.unit}`), unit);
      } catch (error) {
        if (!(error instanceof UnitError)) throw error;
        throw new ExpressionError(`${formatG(other.value)} ${other.unit} can't be compared with ${refText(side)} in ${unit}.`);
      }
    }
    return;
  }
  if (node.kind === "not") checkUnits(node.operand, unitOf);
  else if (node.kind === "and" || node.kind === "or") node.operands.forEach((part) => checkUnits(part, unitOf));
  else if (node.kind === "lit" && node.unit !== null) parseUnit(node.unit);
}
