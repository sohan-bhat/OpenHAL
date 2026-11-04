# Tools for the demo video

The OpenHAL demo video is built in Remotion with React Three Fiber, in `video/remotion/`. No Blender, Cycles or EEVEE runs for the demo. This file lists what is installed for the work and what was checked, as of 2026-11-03.

## Claude Code plugins and skills

| Plugin or skill | Version | State |
|---|---|---|
| Remotion's plugin, `remotion@remotion` | 4.0.540 | Installed and enabled at user scope. The session that builds the video started before the install, so the skill files are read straight from `~/.claude/plugins/cache/remotion/remotion/4.0.540/skills/`, chiefly `remotion-best-practices`, its `remotion-markup` rules for 3D, transitions, audio and fonts, and `remotion-render` |
| Anthropic's frontend-design plugin | 1.1.0 | Installed and enabled. Used for the scenes, cards and redrawn UI |
| digitalsamba's video toolkit | none | Not installed. The brief marks the toolkit optional, and every component here is built on Remotion's own packages |

`remotion-create` was not used to scaffold, because `video/remotion/` already holds a Remotion 4.0.540 project from the stack test in ADR 0022. The demo is a new composition in that project.

## MCP servers

| Server | State |
|---|---|
| Context7 | Connected. Used for the Remotion, `@remotion/three`, React Three Fiber, drei, three.js, `urdf-loader` and glTF Transform APIs |
| Playwright | Connected through the Playwright plugin, `npx @playwright/mcp@latest`. Its configuration is left as the plugin set the server up, with no `--save-video` flag, because the owner asked that the configuration stay unchanged. Scene review uses Remotion's own still and frame renders, and the YouTube study used a headless Playwright script, so no browser window opened |
| Chrome DevTools | Connected through the `chrome-devtools-mcp` plugin, version 1.11.0. Kept for profiling slow frames in the Studio preview |

## Command line tools

| Tool | Version | Where | Use |
|---|---|---|---|
| Node.js | 22.17.1 | `/usr/local/bin/node` | Remotion, the mesh script |
| pnpm | 10.24.0 | `/usr/local/bin/pnpm` | Packages of `video/remotion/` |
| Remotion | 4.0.540 | `video/remotion/node_modules` | `remotion`, `@remotion/cli`, `@remotion/three`, `@remotion/fonts`, and from this video on `@remotion/transitions` and `@remotion/media` |
| React Three Fiber, drei, three.js | 9.8.2, 10.7.9, 0.187.0 | the same | The desk scene |
| urdf-loader | 0.13.1 | the same | Loads The Robot Studio's SO-101 URDF |
| glTF Transform and meshoptimizer | 4.5.1 and 1.3.0 | the same, as dev dependencies | `scripts/simplify-arm.mjs` shrinks the arm's parts to about a quarter of their triangles |
| ffmpeg and ffprobe | 9.0.2, static x86_64 | `~/.local/opt/ffmpeg-9.0.2/bin/` | Frames, loudness, the GIF, joins and checks |
| Playwright | 1.64.1 | `website/node_modules/playwright` | The headless YouTube study in REFERENCE.md |
| Chrome Headless Shell | 158.0.8127.2, mac-x64 | `video/remotion/node_modules/.remotion/` | Remotion's renderer, downloaded by Remotion |

## Remotion settings

Remotion's docs recommend `--gl=angle` for three.js on a desktop with a GPU, and `video/remotion/remotion.config.ts` already sets ANGLE. Renders run with `nice -n 10`, at a concurrency of 1 or 2, scene by scene, as PERF.md logs.

## Remotion license

Remotion's Free License covers an individual, also for commercial use, according to the license file and its FAQ at remotion.dev. The video is made by one person, so no Company License is needed.
