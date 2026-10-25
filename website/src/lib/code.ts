import { LANGUAGE_NAMES, escapeHtml, highlightHtml, languageOf } from "./highlight.mjs";

export function codeHtml(text: string, lang: string, label?: string, tested = false): string {
  const language = languageOf(lang);
  const name = label ?? LANGUAGE_NAMES[language] ?? language.toUpperCase();
  const testedLabel = tested ? `<span class="legend tested">Tested</span>` : "";
  return (
    `<figure class="code-block" data-language="${language}"${tested ? ' data-tested="true"' : ""}>` +
    `<div class="code-head"><span class="labels"><span class="legend">${escapeHtml(name)}</span>${testedLabel}</span></div>` +
    `<pre tabindex="0"><code class="language-${language}">${highlightHtml(text.replace(/\n$/, ""), language)}</code></pre>` +
    `</figure>`
  );
}
