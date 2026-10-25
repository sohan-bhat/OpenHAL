# Decisions

Small decisions, one line each. Architectural decisions live in docs/adr/.

- 2026-10-24 Subagent cap is 3 at once (owner standing rule), stricter than the prompt's 5. Coding agents use Opus 5.5 and never nest subagents.
- 2026-10-24 Python 3.13 is the local interpreter. The package declares requires-python >= 3.12 and CI targets 3.12 and 3.13.
- 2026-10-24 uv installed with `pip install --user uv` (no Homebrew on this machine). Binary at ~/Library/Python/3.13/bin/uv.
- 2026-10-24 Commits are local only, authored by the global git identity, with no trailers. Nothing is pushed.
- 2026-10-24 Hub API port defaults to 7420 on 127.0.0.1. Port 4000 is never used.
- 2026-10-24 Ruff line length is 120, formatting by ruff format.
- 2026-10-24 Spec contract (models, schema, examples) frozen after M1. Later changes go through an ADR.
- 2026-10-24 Human principals count as confirmers for their own commands. Routines can't satisfy a confirmation except through a signed approval on a high hazard device. Agents need control_medium to request high hazard commands, which always queue.
- 2026-10-24 zeroconf (LGPL-2.1-or-later) is used unmodified as a dependency for mDNS discovery.
- 2026-10-24 While subagents share the working tree, commits stage explicit paths only, never git add -A.
- 2026-10-24: The README flow diagram uses D2 grid layout plus a post-processing script (scripts/build-diagrams). ELK and dagre could not keep the main path on one line, and draw.io Desktop is not installed.
- 2026-10-24: The flow diagram has a vertical variant for screens under 600 px, chosen by <picture> media queries, so the diagram stays readable on phones.
- 2026-10-25: The CI badge is back on the README because the owner asked to keep the license and CI badges.
- 2026-10-25: The kernel's Python API still parses quantity strings for routines and other human-written inputs. Every wire entry point calls it with wire=True, which refuses them (ADR 0016).
- 2026-10-25: The plant waterer's mock file ships confirmed by sohan on 2026-10-24 so the demo can water. The real board's file and the copy `openhal init` makes ship unconfirmed, so every owner confirms their own hardware.
- 2026-10-25: The plant waterer has a stop action besides water, because its safe state (pump off) has to be an action of the file.
- 2026-10-25: `openhal demo` runs the simulated board 40 times faster than real time, and `--real-time` runs it at real speed. Heartbeats always use real time.
- 2026-10-25: The scenario record leaves out times, so two runs give the same file and a test can rerun the hub and compare.
- 2026-10-25: In user-facing text a write channel is a control channel. Method names (hal/write), the `openhal write` command and the device file's `write:` section keep their names.
- 2026-10-25: python-can (LGPL-3.0-only) is used unmodified as an optional dependency of the can driver, like zeroconf. No code is copied.
