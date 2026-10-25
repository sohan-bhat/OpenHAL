# Install timing

The goal is under 60 seconds from installing OpenHAL to the first agent read of a self-describing device. Both runs below meet it with room to spare.

Recorded on 2026-10-25 on an Intel Mac (Core i7-8750H, 12 threads, 16 GB, macOS 15.5) with uv 0.13.5 and Python 3.13.2. Two other agents were working on the machine at the time, with a load average near 4.

## scripts/time-first-read

The script builds the wheel, installs it into a fresh temporary tool folder, runs `openhal init --yes --no-discover --no-sample --device openhal-firmware=sim:plant-waterer` in a temporary HOME, starts `openhald` on a free loopback port and starts `openhal mcp` the way an AI client does. The agent calls `list_devices`, then `read` on `plant-waterer.soil_moisture`. Init doesn't run discovery, so nothing probes the machine's ports or network. The simulated plant waterer stands in for a board discovery finds on a serial port, and it describes itself over the real firmware protocol. `--no-sample` leaves out the sample file, so the board is added the way a real self-describing board is.

Run 1, uv tool install with a warm package cache.

| Step | Time | What happened |
|---|---|---|
| build | 1.14 s | `uv build --wheel` made openhal_hub-0.1.0.dev0-py3-none-any.whl |
| install | 2.00 s | `uv tool install --compile-bytecode` into a temporary tool folder |
| init | 2.66 s | config folder, human token, plant-waterer added read-only, agent token, client setup printed |
| hub | 2.12 s | `openhald` answered at 127.0.0.1 |
| first read | 2.83 s | `list_devices`, then `read` gave plant-waterer.soil_moisture = 31.0 % |
| install to first read | 9.61 s | |

Run 2, the same.

| Step | Time | What happened |
|---|---|---|
| build | 0.78 s | |
| install | 1.39 s | |
| init | 2.29 s | |
| hub | 2.03 s | |
| first read | 2.79 s | plant-waterer.soil_moisture = 31.0 % |
| install to first read | 8.50 s | |

Earlier runs of the script on the same day, with a busier machine and the previous sample board.

| Run | Install to first read | Notes |
|---|---|---|
| Quieter machine | 10.53 s | install 1.84 s, init 3.60 s, hub 1.77 s, first read 3.32 s |
| pipx install | 24.46 s | pipx 1.18 with its default uv backend. Init and the first read took about 9 s each, as without `--compile-bytecode` |
| Empty package cache | 18.91 s | needs `--no-build` on an Intel Mac, see below |
| Without `--compile-bytecode` | 21.29 s | init 8.66 s and first read 8.57 s, compiling on first import |

## What was slow, and the fix

The first run of every command compiled its imports, which made init and the first read take 8 to 9 seconds each. `uv tool install --compile-bytecode` moves that work into the install, which uv does in parallel. It cut the install to first read from 21.29 s to 10.53 s on a quiet machine. The timing script, the install guide and the Pi script use it.

What is left is import time in code this workstream doesn't own. Every `openhal` command imports `openhal.client`, which builds the pint unit registry, about 0.4 s. `openhal mcp` also imports the MCP SDK, about 1.3 s. See the proposals in the packaging report.

## Intel Mac with an empty cache

cryptography 50.0.2, which comes in through mcp and pyjwt, and zeroconf 0.151.5 publish macOS wheels for Apple Silicon only. With an empty cache, `uv tool install` tries to build cryptography and fails because it needs Rust. pipx's pip backend fails the same way. Two fixes work.

- `uv tool install --no-build` picks versions that ship wheels. The run took 4.47 s to install and 18.91 s to the first read.
- `pipx install --pip-args=--only-binary=:all:` does the same with pip, in 129 s.

Apple Silicon and Linux get wheels for every core dependency.

## Fresh install from the README

The README's quickstart, followed as written in an empty folder, with the clone made from this repository's local path instead of GitHub.

| Step | Warm cache | Empty cache |
|---|---|---|
| `git clone` | 3.38 s | 2.24 s |
| `cd OpenHAL` | | |
| `uv run openhal demo` | 14.64 s | 113.75 s |
| Total | 18.02 s | 115.99 s |

`uv run` made `.venv` and installed 70 packages, then the demo printed the trace. The outcome matched the README's sentence. The hub refused the 120 s watering with LIMIT_EXCEEDED, held the pump with INTERLOCK_BLOCKED while the tank was empty, then watered for 20 s as soil moisture rose from 31 % to 46 %. With an empty cache, uv built zeroconf from source, which took most of the 114 s. The lock file already pins a cryptography with Intel Mac wheels.

What the README got wrong or left out.

1. It doesn't say you need uv and git. docs/guide/quickstart.md says so, the README doesn't, and `uv run` is the first thing that fails on a fresh machine.
2. The trace in the README uses `→` and `←`, and the terminal prints `->` and `<-`. The README calls it a real run, and the words match, but a reader comparing them sees different arrows.
3. `uv run` also installs the dev group, such as pytest, mypy, ruff and hypothesis, which the demo doesn't need. In another fresh clone, `uv run --no-dev openhal demo` installed 49 packages instead of 70 and took 10.06 s instead of 14.64 s.
4. It stops at the demo. Nothing points to installing OpenHAL, `openhal init` or connecting an AI client, which is the path to a first agent read.
