import { useMemo } from "react";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";
import { yaml } from "@codemirror/lang-yaml";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";

/** The house syntax theme (docs/DESIGN.md, Syntax theme) from the tokens, so both themes follow the page. */
const house = HighlightStyle.define([
  { tag: [tags.definition(tags.propertyName), tags.propertyName], color: "var(--syn-key)" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--syn-string)" },
  { tag: [tags.content, tags.number, tags.bool, tags.null, tags.attributeValue], color: "var(--syn-number)" },
  { tag: [tags.separator, tags.punctuation, tags.squareBracket, tags.brace, tags.meta], color: "var(--syn-punct)" },
  { tag: [tags.keyword, tags.labelName, tags.typeName], color: "var(--syn-method)", fontWeight: "700" },
  { tag: [tags.comment, tags.lineComment], color: "var(--syn-comment)", fontStyle: "italic" },
]);

/** The field's frame, the site's 1.5 px control outline on the surface, with the accent focus ring. */
const frame = EditorView.theme({
  "&": {
    color: "var(--text)",
    backgroundColor: "var(--surface)",
    border: "1px solid var(--oh-control-border)",
    boxShadow: "var(--oh-control-ring) var(--oh-control-border)",
    borderRadius: "var(--radius)",
    fontSize: "14px",
  },
  "&.cm-focused": { outline: "2px solid var(--accent)", outlineOffset: "2px" },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.6", overflowX: "hidden" },
  ".cm-content": { padding: "var(--s-3) 0", caretColor: "var(--text)" },
  ".cm-content:focus-visible": { outline: "none" },
  ".cm-line": { padding: "0 var(--s-3)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--text)" },
});

const SETUP = {
  lineNumbers: false,
  foldGutter: false,
  highlightActiveLine: false,
  highlightActiveLineGutter: false,
  highlightSpecialChars: true,
  history: true,
  drawSelection: false,
  dropCursor: false,
  allowMultipleSelections: false,
  indentOnInput: false,
  syntaxHighlighting: false,
  bracketMatching: false,
  closeBrackets: false,
  autocompletion: false,
  rectangularSelection: false,
  crosshairCursor: false,
  highlightSelectionMatches: false,
  closeBracketsKeymap: false,
  defaultKeymap: true,
  searchKeymap: false,
  historyKeymap: true,
  foldKeymap: false,
  completionKeymap: false,
  lintKeymap: false,
  tabSize: 2,
};

const BASE = [yaml(), syntaxHighlighting(house), frame, EditorView.lineWrapping];

interface Props {
  value: string;
  onChange: (value: string) => void;
  id: string;
  label: string;
  describedBy: string;
}

/**
 * The device file's editor, CodeMirror 6 through @uiw/react-codemirror, with YAML highlighting in
 * the house theme. Lines wrap and there are no line numbers, the way the text field showed the file,
 * and Tab leaves the editor because no key binding takes Tab, so a keyboard user never gets trapped.
 */
export default function DeviceEditor({ value, onChange, id, label, describedBy }: Props) {
  const extensions = useMemo(
    () => [...BASE, EditorView.contentAttributes.of({ id, "aria-label": label, "aria-describedby": describedBy, spellcheck: "false", autocapitalize: "off", autocorrect: "off" })],
    [id, label, describedBy],
  );
  return <CodeMirror className="pg-editor" value={value} onChange={onChange} theme="none" indentWithTab={false} basicSetup={SETUP} extensions={extensions} />;
}
