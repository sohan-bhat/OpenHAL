# Render performance of the demo video

Every render of the demo runs on the 2018 MacBook Pro described in video/README.md, an Intel Core i7-8750H with 6 cores, 16 GB of RAM and a Radeon Pro 555X. The demo never starts Blender. Each heavy job runs alone, under `nice -n 10`, and `pmset -g therm` is read before and after each one.

## Settings

| Setting | Value |
|---|---|
| Design size | 1280 by 720, 30 fps |
| Output scale | `--scale=2` for 2560 by 1440, `--scale=1.5` for 1920 by 1080 |
| WebGL | `--gl=angle`, Remotion's recommendation for three.js on a desktop |
| 3D canvas | 716 by 536 in the design, drawn at the render scale through `usePixelDensity()`, so 1432 by 1072 at 1440p |
| Concurrency | 2 browser tabs |
| Encoder | H.264, CRF 18, yuv420p |
| Bundle | `remotion bundle` once into `video/out/demo/bundle/`, then every render reads that bundle |

## 3D budget

| Item | Budget | Used |
|---|---|---|
| Triangles | under 150,000 | 139,871 for the arm after `scripts/simplify-arm.mjs` at a ratio of 0.35 and an error of 0.001, from 398,529 in the source parts, plus about 600 for the desk, the bin and the cube |
| Shadow casting lights | at most 2 | 1, a spot light with a 2048 by 2048 shadow map |
| Other lights | | a directional rim light and a hemisphere light, no shadows |
| HDRI | one, low resolution, CC0 | `studio_small_09_2k.hdr` from Poly Haven, for reflections only |
| Post processing | none heavy | none, only ACES tone mapping and the canvas's own antialiasing |

## Measurements

| Date | Render | Frames | Wall time | Per frame | CPU speed limit before and after |
|---|---|---|---|---|---|
| 2026-11-03 19:13 | `DeskTest` at 1440p, concurrency 2, with bundling and the arm at a ratio of 0.25 | 90 | 30 s | 0.33 s | 58 and 56 percent |
| 2026-11-03 19:14 | `DeskTest` at 1440p, concurrency 2, from the bundle, the arm at a ratio of 0.25 | 90 | 18.0 s | 0.20 s | 100 and 100 percent |
| 2026-11-03 19:15 | `DeskTest` at 1440p, concurrency 2, from the bundle, the arm at a ratio of 0.35 | 90 | 18.0 s | 0.20 s | 100 and 100 percent |

The wall time includes starting the browser, loading the arm, the HDRI and the wood texture, and encoding. Bundling took 5 s. The first test started at a 58 percent speed limit left over from the stills rendered just before, and the limit was back at 100 percent 20 s after the render ended.

At 0.2 s a frame, the whole video at about 1,500 frames takes about 5 minutes at 1440p, so the final renders still go scene by scene with a pause between scenes to keep the laptop cool.
