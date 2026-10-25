const PATTERNS = {
  json: [
    ["str", /"(?:[^"\\]|\\.)*"/y],
    ["num", /-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b(?:true|false|null)\b/y],
    ["punct", /[{}[\],:]/y],
  ],
  yaml: [
    ["comment", /#.*/y],
    ["str", /"(?:[^"\\]|\\.)*"|'[^']*'/y],
    ["num", /(?<![\w.:/-])-?\d+(?:\.\d+)?(?![\w:.-])|\b(?:true|false|null)\b/y],
    ["punct", /[{}[\],]|^\s*-(?=\s)/y],
  ],
  sh: [
    ["comment", /(?<=^|\s)#.*/y],
    ["str", /"(?:[^"\\]|\\.)*"|'[^']*'/y],
  ],
  python: [
    ["comment", /#.*/y],
    ["str", /"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/y],
    ["num", /\b\d+(?:\.\d+)?\b|\b(?:True|False|None)\b/y],
    ["punct", /[()[\]{}:,.]/y],
  ],
  ts: [
    ["str", /`(?:[^`\\]|\\.)*`|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/y],
    ["num", /\b\d+(?:\.\d+)?\b|\b(?:true|false|null|undefined)\b/y],
    ["punct", /[()[\]{}:;,.]/y],
  ],
};

const ALIASES = { bash: "sh", shell: "sh", console: "sh", yml: "yaml", py: "python", js: "ts", javascript: "ts", typescript: "ts" };

export function languageOf(lang) {
  const name = (lang ?? "").toLowerCase();
  return ALIASES[name] ?? name;
}

function scan(text, patterns) {
  const tokens = [];
  let plain = "";
  let i = 0;
  while (i < text.length) {
    let matched = null;
    for (const [cls, pattern] of patterns) {
      pattern.lastIndex = i;
      const found = pattern.exec(text);
      if (found && found[0].length > 0) {
        matched = [cls, found[0]];
        break;
      }
    }
    if (matched) {
      if (plain) tokens.push(["", plain]);
      plain = "";
      tokens.push(matched);
      i += matched[1].length;
    } else {
      plain += text[i];
      i += 1;
    }
  }
  if (plain) tokens.push(["", plain]);
  return tokens;
}

function jsonKeys(tokens) {
  for (let index = 0; index < tokens.length; index++) {
    if (tokens[index][0] !== "str") continue;
    let next = index + 1;
    while (next < tokens.length && tokens[next][0] === "" && tokens[next][1].trim() === "") next++;
    if (tokens[next] && tokens[next][0] === "punct" && tokens[next][1] === ":") tokens[index][0] = "key";
  }
  return tokens;
}

function yamlLine(line) {
  const key = /^(\s*(?:-\s+)?)([A-Za-z_][\w.-]*|"[^"]*")(\s*:)(?=\s|$)/.exec(line);
  if (!key) return scan(line, PATTERNS.yaml);
  const tokens = [];
  if (key[1]) tokens.push(...scan(key[1], PATTERNS.yaml));
  tokens.push(["key", key[2]], ["punct", key[3]]);
  const rest = line.slice(key[0].length);
  const inline = /^(\s*\{)/.exec(rest);
  if (inline) {
    for (const part of rest.split(/(\b[A-Za-z_][\w-]*(?=:\s))/)) {
      if (/^[A-Za-z_][\w-]*$/.test(part) && rest.includes(`${part}:`)) tokens.push(["key", part]);
      else tokens.push(...scan(part, PATTERNS.yaml));
    }
    return tokens;
  }
  if (/^\s*[A-Za-z]/.test(rest) && !/^\s*(?:true|false|null)\s*$/.test(rest)) tokens.push(["", rest]);
  else tokens.push(...scan(rest, PATTERNS.yaml));
  return tokens;
}

function yamlLines(text) {
  let block = null;
  return text.split(/(?<=\n)/).flatMap((line) => {
    const indent = /^\s*/.exec(line)[0].length;
    if (block !== null && (!line.trim() || indent > block)) return [["", line]];
    block = /:\s*[>|][-+]?\s*$/.test(line) ? indent : null;
    return yamlLine(line);
  });
}

function shLines(text) {
  return text.split(/(?<=\n)/).flatMap((line) => {
    const prompt = /^\$ /.exec(line);
    if (!prompt) return [["", line]];
    return [["prompt", "$ "], ...scan(line.slice(2), PATTERNS.sh)];
  });
}

export function tokenize(text, lang) {
  const language = languageOf(lang);
  if (language === "json") return jsonKeys(scan(text, PATTERNS.json));
  if (language === "yaml") return yamlLines(text);
  if (language === "sh") return shLines(text);
  if (language === "python" || language === "ts") return scan(text, PATTERNS[language]);
  return [["", text]];
}

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

export function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (char) => ESCAPES[char]);
}

export function highlightHtml(text, lang) {
  return tokenize(text, lang)
    .map(([cls, value]) => (cls ? `<span class="syn-${cls}">${escapeHtml(value)}</span>` : escapeHtml(value)))
    .join("");
}

export const LANGUAGE_NAMES = {
  sh: "Shell",
  yaml: "YAML",
  json: "JSON",
  python: "Python",
  ts: "TypeScript",
  cpp: "C++",
  ini: "INI",
  text: "Text",
  "": "Text",
};
