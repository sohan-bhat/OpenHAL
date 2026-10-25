function shortest(x: number): { digits: string; exp: number } {
  const text = Math.abs(x).toExponential();
  const [mantissa, exponent] = text.split("e");
  return { digits: mantissa.replace(".", ""), exp: Number(exponent) };
}

function special(x: number): string | null {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  return null;
}

function sign(x: number): string {
  return x < 0 || Object.is(x, -0) ? "-" : "";
}

function exponentText(exp: number): string {
  const magnitude = String(Math.abs(exp)).padStart(2, "0");
  return `e${exp < 0 ? "-" : "+"}${magnitude}`;
}

export function pyFloatRepr(x: number): string {
  const odd = special(x);
  if (odd) return odd;
  if (x === 0) return `${sign(x)}0.0`;
  const { digits, exp } = shortest(x);
  if (exp < -4 || exp >= 16) {
    const mantissa = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    return `${sign(x)}${mantissa}${exponentText(exp)}`;
  }
  let text: string;
  if (exp >= 0) {
    const whole = digits.length > exp + 1 ? digits.slice(0, exp + 1) : digits.padEnd(exp + 1, "0");
    const fraction = digits.length > exp + 1 ? digits.slice(exp + 1) : "0";
    text = `${whole}.${fraction}`;
  } else {
    text = `0.${"0".repeat(-exp - 1)}${digits}`;
  }
  return `${sign(x)}${text}`;
}

export function pyStr(value: unknown): string {
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") return pyFloatRepr(value);
  if (typeof value === "bigint") return value.toString();
  if (value === null || value === undefined) return "None";
  return String(value);
}

export function formatG(x: number, precision = 6): string {
  const odd = special(x);
  if (odd) return odd;
  const p = precision === 0 ? 1 : precision;
  if (x === 0) return `${sign(x)}0`;
  const [mantissa, exponent] = Math.abs(x).toExponential(p - 1).split("e");
  const exp = Number(exponent);
  let body: string;
  if (exp >= -4 && exp < p) {
    body = Math.abs(x).toFixed(Math.max(0, p - 1 - exp));
    if (body.includes(".")) body = body.replace(/0+$/, "").replace(/\.$/, "");
  } else {
    let m = mantissa;
    if (m.includes(".")) m = m.replace(/0+$/, "").replace(/\.$/, "");
    body = `${m}${exponentText(exp)}`;
  }
  return `${sign(x)}${body}`;
}

export function formatF(x: number, digits: number): string {
  const odd = special(x);
  if (odd) return odd;
  return `${sign(x)}${Math.abs(x).toFixed(digits)}`;
}

export function pyStrRepr(text: string): string {
  const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
  let out = "";
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    if (char === "\\") out += "\\\\";
    else if (char === quote) out += `\\${quote}`;
    else if (char === "\n") out += "\\n";
    else if (char === "\r") out += "\\r";
    else if (char === "\t") out += "\\t";
    else if (code < 0x20 || code === 0x7f) out += `\\x${code.toString(16).padStart(2, "0")}`;
    else out += char;
  }
  return `${quote}${out}${quote}`;
}

export function isClose(a: number, b: number, relTol = 1e-9, absTol = 0): boolean {
  if (a === b) return true;
  if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
  const diff = Math.abs(a - b);
  return diff <= Math.max(relTol * Math.max(Math.abs(a), Math.abs(b)), absTol);
}

export function pyRound(x: number): number {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}
