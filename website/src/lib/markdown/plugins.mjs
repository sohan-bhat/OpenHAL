// Markdown plugins for rendering the repository's own documents on the site.

import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { visit } from "unist-util-visit";
import { routeFor } from "./routes.mjs";

export const REPO_ROOT = fileURLToPath(new URL("../../../../", import.meta.url));

function textOf(node) {
  if (node.type === "text" || node.type === "inlineCode") return node.value;
  return (node.children ?? []).map(textOf).join("");
}

/** Move the first level one heading into frontmatter as `title`, so the page header shows it once. */
export function remarkTitle() {
  return (tree, file) => {
    const index = tree.children.findIndex((node) => node.type === "heading" && node.depth === 1);
    if (index === -1) return;
    const title = textOf(tree.children[index]);
    tree.children.splice(index, 1);
    file.data.astro ??= {};
    file.data.astro.frontmatter ??= {};
    file.data.astro.frontmatter.title ??= title;
  };
}

/** Point links between repository documents at their pages on the site. Unpublished targets become text. */
export function remarkRepoLinks() {
  return (tree, file) => {
    const source = file.path ? resolve(file.path) : null;
    if (!source) return;
    visit(tree, "link", (node, index, parent) => {
      const url = node.url;
      if (/^[a-z]+:/i.test(url) || url.startsWith("#") || url.startsWith("/")) return;
      const [path, hash] = url.split("#");
      const repoPath = relative(REPO_ROOT, resolve(dirname(source), path)).split("\\").join("/");
      const route = routeFor(repoPath);
      if (route) {
        node.url = hash ? `${route}#${hash}` : route;
      } else if (parent && index !== undefined) {
        parent.children.splice(index, 1, { type: "inlineCode", value: textOf(node) || repoPath });
      }
    });
  };
}

const LANGUAGE_NAMES = {
  sh: "Shell",
  bash: "Shell",
  console: "Shell",
  shell: "Shell",
  yaml: "YAML",
  json: "JSON",
  python: "Python",
  py: "Python",
  cpp: "C++",
  ini: "INI",
  text: "Text",
};

function classList(node) {
  const value = node.properties?.className;
  return Array.isArray(value) ? value.map(String) : value ? String(value).split(" ") : [];
}

/** Wrap code blocks in a labelled module, mark tested snippets and set shell prompts apart. */
export function rehypeCodeBlocks() {
  return (tree) => {
    visit(tree, "element", (node, index, parent) => {
      if (node.tagName !== "pre" || !parent || index === undefined) return;
      const code = node.children.find((child) => child.type === "element" && child.tagName === "code");
      if (!code) return;
      const language = classList(code).find((name) => name.startsWith("language-"))?.slice(9) ?? "text";
      const meta = String(code.data?.meta ?? "");
      const tested = /(^|\s)tested(\s|$)/.test(meta);
      const shell = ["sh", "bash", "console", "shell"].includes(language);
      if (shell) {
        const text = code.children.map((child) => (child.type === "text" ? child.value : "")).join("");
        code.children = text.split(/(?<=\n)/).flatMap((line) => {
          const match = /^(\$ )(.*)$/s.exec(line);
          if (!match) return [{ type: "text", value: line }];
          return [
            { type: "element", tagName: "span", properties: { className: ["prompt"], ariaHidden: "true" }, children: [{ type: "text", value: "$ " }] },
            { type: "element", tagName: "span", properties: { className: ["command"] }, children: [{ type: "text", value: match[2] }] },
          ];
        });
      }
      const legend = [LANGUAGE_NAMES[language] ?? language.toUpperCase()];
      const caption = {
        type: "element",
        tagName: "figcaption",
        properties: { className: ["code-legend"] },
        children: [
          { type: "element", tagName: "span", properties: {}, children: [{ type: "text", value: legend[0] }] },
          ...(tested
            ? [
                {
                  type: "element",
                  tagName: "span",
                  properties: { className: ["tested"], title: "Run against the real CLI by tests/website/test_snippets.py" },
                  children: [{ type: "text", value: "Tested" }],
                },
              ]
            : []),
        ],
      };
      node.properties = { ...node.properties, tabIndex: 0 };
      parent.children[index] = {
        type: "element",
        tagName: "figure",
        properties: { className: ["code-block"], dataLanguage: language, ...(tested ? { dataTested: "true" } : {}) },
        children: [caption, node],
      };
      return "skip";
    });
  };
}

/** Label every table cell with its column header, so narrow screens can show rows as label and value pairs. */
export function rehypeTables() {
  return (tree) => {
    visit(tree, "element", (node, index, parent) => {
      if (node.tagName !== "table" || !parent || index === undefined) return;
      const headers = [];
      visit(node, "element", (cell) => {
        if (cell.tagName === "th") headers.push(textOfHast(cell));
      });
      visit(node, "element", (row) => {
        if (row.tagName !== "tr") return;
        let column = 0;
        for (const cell of row.children) {
          if (cell.type !== "element" || cell.tagName !== "td") continue;
          cell.properties = { ...cell.properties, dataLabel: headers[column] ?? "" };
          column += 1;
        }
      });
      parent.children[index] = {
        type: "element",
        tagName: "div",
        properties: { className: ["table-wrap"] },
        children: [node],
      };
      return "skip";
    });
  };
}

function textOfHast(node) {
  if (node.type === "text") return node.value;
  return (node.children ?? []).map(textOfHast).join("");
}
