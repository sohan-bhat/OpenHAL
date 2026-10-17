# Decisions

Small decisions, one line each. Architectural decisions live in docs/adr/.

- 2026-10-24 Subagent cap is 3 at once (owner standing rule), stricter than the prompt's 5. Coding agents use Opus 5.5 and never nest subagents.
- 2026-10-24 Python 3.13 is the local interpreter. The package declares requires-python >= 3.12 and CI targets 3.12 and 3.13.
- 2026-10-24 uv installed with `pip install --user uv` (no Homebrew on this machine). Binary at ~/Library/Python/3.13/bin/uv.
- 2026-10-24 Commits are local only, authored by the global git identity, with no trailers. Nothing is pushed.
- 2026-10-24 Hub API port defaults to 7420 on 127.0.0.1. Port 4000 is never used.
