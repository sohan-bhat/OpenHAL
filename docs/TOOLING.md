# Tooling

Tools used to build, check and document OpenHAL. None of them is a runtime dependency of OpenHAL.

## Claude Code plugins

| Plugin | Marketplace | Version | Used for |
|---|---|---|---|
| frontend-design | claude-plugins-official and claude-code-plugins | 1.1.0 | Design direction for the website, Inspector and diagrams |
| playwright | claude-plugins-official | installed | Screenshots and cross-browser checks |
| context7 | claude-plugins-official | installed | Current docs for D2, SVGO and every library |
| chrome-devtools-mcp | claude-plugins-official | 1.11.0 | Console, network and performance checks |
| typescript-lsp | claude-plugins-official | installed | TypeScript language server |

## Skills

| Skill | Source | Location |
|---|---|---|
| d2-diagrams | `npx skills add https://github.com/boazy/skills --skill d2-diagrams` | `~/code/.agents/skills/d2-diagrams`, linked for Claude Code. Two Markdown files, reviewed before use |

## Diagram toolchain

| Tool | Version | License | How it is installed | Used for |
|---|---|---|---|---|
| D2 CLI | v0.9.0 | MPL-2.0 | Release binary from github.com/d2lang/d2 in `~/.local/opt`, linked as `~/.local/bin/d2` | Grid layout of every diagram in docs/diagrams |
| SVGO | 4.1.0 | MIT | `npx --yes svgo@4.1.0`, pinned in scripts/diagrams.py | Optimizing the SVGs, config in scripts/svgo.config.mjs |
| fonttools | 4.67.0 | MIT | `uv run --with fonttools==4.67.0 --with brotli` | Static TTFs from the variable fonts for D2, and text as paths for the wordmark |
| Playwright Chromium headless shell | 1248 | Apache-2.0 | Existing Playwright browser cache | Rendering the README in GitHub's light and dark modes |
| github-markdown-css | 5.8.1 | MIT | Downloaded for local previews only | The README preview |

`scripts/build-diagrams` builds every diagram in docs/diagrams in light and dark. That is the flow diagram from `flow.d2` with narrow variants for phones, the seven architecture diagrams (`architecture-*.d2`) and the spec's exchange (`spec-exchange.d2`), which share `house.d2`. D2 places the nodes on a grid. The script then applies the house style: our fonts, 1.5 px strokes, labels above their lines, the return line routed with right angles only, a transparent background, title and description, and the flowing dash animation with a `prefers-reduced-motion` rule.

The architecture and spec diagrams redraw Mermaid blocks in docs/ARCHITECTURE.md and the spec. When you edit one of those blocks, update its `.d2` file, run `scripts/build-diagrams`, and let it refresh `docs/diagrams/diagrams.json`, which records the Mermaid text each redraw belongs to. Until then the website shows the plain Mermaid and `website/tests/unit/diagrams.test.ts` fails.

## Not used

- **draw.io plugin.** The D2 grid layout gave a clean result, and draw.io Desktop (needed for SVG export) is not installed.
- **Mermaid CLI.** It was the fallback, and D2 made it unnecessary.
- **D2 ELK and dagre automatic layouts.** They could not keep the five nodes on one line with Blocked below the kernel. The grid layout does.
