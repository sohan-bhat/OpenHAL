import { highlightLinesHtml, languageOf } from "./highlight.mjs";

export function codeHtml(text: string, lang: string, tested = false): string {
  const language = languageOf(lang);
  return (
    `<figure class="code-block" data-language="${language}"${tested ? ' data-tested="true"' : ""}>` +
    `<pre tabindex="0"><code class="language-${language}">${highlightLinesHtml(text.replace(/\n$/, ""), language)}</code></pre>` +
    `</figure>`
  );
}
