# 0022 The launch film renders its 3D in Blender, and its type and edit in Remotion

## Context

The launch film shows OpenHAL on the SO-101 arm, drawn entirely in code. It needs studio lighting, real materials, slow camera moves, almost no text, and it has to render on the machine that makes it, a 2018 MacBook Pro (Intel Core i7-8750H, 16 GB, Radeon Pro 555X, about 10 GB of free disk). On 2026-11-03 the same 5-second test shot was built in the two strongest stacks and rendered at 3840 by 2160. The shot is the SO-101 picking up a cube on a desk under studio lighting with a slow camera dolly. Both stacks read one shot file, one look file and the official SO-101 URDF, so they render the same motion, materials and lights. The motion is hand-keyed for the test, not hub data.

1. **Blender 4.5.15 LTS**, scripted with Python and run headless, in `video/scenes/`. Cycles on the CPU and EEVEE on the GPU.
2. **Remotion 4.0.540 with React Three Fiber and three.js**, in `video/remotion/`, with physically based materials, the Poly Haven studio HDRI, PCSS soft shadows, N8AO ambient occlusion, depth of field, AgX tone mapping, light grain and a little bloom.

Every number below comes from this machine on 2026-11-03. During the runs macOS held the CPU at 26 to 29 percent of its rated speed (`pmset -g therm`, CPU_Speed_Limit), and other agents ran builds and browser tests at the same time. A cooler, idle machine would render faster.

## Comparison

### Quality, frame by frame

The comparison image `video/out/test/compare-f094.png` shows frame 94 from each stack with 100 percent crops of the gripper. Frames 1 and 150 from each stack are in `video/out/test/` as well.

| | Cycles | EEVEE | Remotion and three.js |
|---|---|---|---|
| Light and shadow | Soft contact shadows, light bouncing between the arm's parts and off the desk, smooth falloff | Close to Cycles. Slightly less bounce light in the gaps between parts | Shadows from one key light only. No light bounces between parts, so the arm reads flatter, and the far edge of the desk shows as a hard line |
| Materials | The printed plastic, servo housings and cables look like objects on a desk | Nearly the same as Cycles in the full frame. At 100 percent the moving jaw shows fine speckle and a thin light leak along one edge | Clean, yet the plastic reads as computer graphics next to the Blender frames, with faint shadow stripes on the moving jaw |
| Depth of field | Physically correct, from the camera's f-stop | Physically based, close to Cycles | A screen-space blur. The gripper, a few centimeters from the focus point, comes out soft where Blender keeps it sharp. A stronger blur, to match Blender's background, put a halo around the arm and left the far desk edge sharp |
| Motion blur | Yes, from the real motion | Yes | None. three.js has no motion blur, and a fix means rendering several subframes for each frame |
| Noise | 16 samples and OpenImageDenoise leave a clean 4K frame | 16 samples leave a clean frame | None |

Frames 1, 94 and 150 agree. Cycles looks best, EEVEE is a close second, and the WebGL frame is clearly behind. The difference grows in motion, where Blender has motion blur and three.js has none.

### Render time per 4K frame

| Stack | Settings | Seconds per 4K frame | 150 frames at 4K |
|---|---|---|---|
| Cycles, CPU | 16 samples, adaptive, OpenImageDenoise, motion blur, depth of field | 725 | 30 hours |
| EEVEE, GPU | 32 samples | 78 | 3.2 hours |
| EEVEE, GPU | 16 samples, used for the full test | 53 (36 at best) | 2.2 hours |
| Remotion, WebGL | concurrency 1, PNG frames, H.264 | 2.3 | 6 minutes |

Most runs shared the machine with another render. The Cycles figure and the EEVEE 32-sample figure come from runs with no other render going, and the same Cycles frame took 1122 seconds while EEVEE and Remotion also ran. EEVEE's 53 seconds is the median of the full test, with Cycles on the CPU at the same time. Remotion took 2.3 seconds a frame with Cycles on the CPU and 6.8 seconds a frame while EEVEE also held the GPU.

Cycles can't use the GPU here. Blender 4.5 lists only the CPU for Metal, and according to the Blender 4.5 manual, Metal rendering works on Apple Silicon only. A full Cycles test shot at 4K would take about 30 hours, and a 1080p pass with 6 samples ran at about 105 seconds a frame while EEVEE shared the machine. A moving Cycles version could never serve a 60-second film here, so Cycles rendered three key frames at 4K, the start (frame 1), the grip (frame 94) and the end (frame 150), to show the quality ceiling. EEVEE at 32 samples would pass 3 hours, so EEVEE rendered the whole shot at 4K with 16 samples. Remotion rendered the whole shot at 4K.

### Iteration speed

- Blender builds the whole scene from scripts, with 150 frames of keys, in about 30 seconds on the loaded machine. A 960 by 540 preview frame takes 3 to 7 seconds in EEVEE and about 37 seconds in Cycles. The first EEVEE render on a new machine spent 3.5 minutes compiling shaders, and an EEVEE render started while another one held the GPU spent 4.5 minutes the same way.
- Remotion bundles in about 20 seconds, and a quarter-size still takes about 37 seconds from the command line, bundling included. Remotion Studio offers live preview, which this headless test didn't use.
- Two bugs in the Remotion scene code cost time. A render hold created during a React Suspense render was lost and stalled the render for 4 minutes, and the arm's parts reached the scene after the frame was captured. Both fixes are in `video/remotion/src/so101.ts`. Blender errors arrive as plain Python tracebacks.

### Text and labels

- **Remotion** sets text as web type. IBM Plex Sans and Plex Mono load from the repository's WOFF2 files with every weight of the variable Sans, kerning and tabular numbers, and text animates with the same frame clock as the 3D. The comparison image is a Remotion still.
- **Blender** loads the same WOFF2 files as 3D text objects, which take the scene's light, depth of field and motion blur. A variable font gives only its default instance, so other weights need static Plex files, and layout is done by hand in scene units.
- **ffmpeg** `drawtext` stalled on fontconfig in this static build, so it isn't a text tool here.

### License

- **Blender** is GPL-2.0-or-later, and Cycles is Apache-2.0. Renders belong to whoever makes them, with no restriction. Scripts that use Blender's Python API must be published under a GPL-compatible license. Apache-2.0 is compatible with GPL-3.0, and Blender's license allows GPL-3.0, so the scene scripts in `video/scenes/` stay Apache-2.0 like the rest of the repository.
- **Remotion** uses the Remotion License, source-available and not an OSI license. It is free for individuals, for-profit organizations with up to 3 employees, non-profits and evaluation, commercial use included. Larger companies need a Company License from remotion.pro. The license for Remotion 5.0 will also count contractors toward team size. The film's owner is an individual, so the film qualifies for the free license. A contributor at a larger company would need a Company License to render the Remotion parts. `@remotion/three` is MIT.
- **three.js, React Three Fiber and drei** are MIT, postprocessing is Zlib, n8ao is ISC and urdf-loader is Apache-2.0.

## Decision

The film renders every 3D shot in Blender from scripts. EEVEE renders the moving shots, and Cycles renders stills and held frames, where one frame covers a whole hold. Remotion sets the type, draws the flat graphics of the OpenHAL layer and assembles the edit from Blender's frame sequences. ffmpeg encodes the intermediates and the masters.

Blender gives the better frame. Its light, contact shadows, depth of field and motion blur look like a product film, and three.js stays visibly behind even with every effect on. Remotion stays for the 2D layer because its type handling is the best of the three, and a 4K frame took about 2 seconds even with the whole 3D test scene in it.

## Render plan for the full film

The film is about 60 seconds at 30 frames a second, 1800 frames at 3840 by 2160, plus a vertical cut at 1080 by 1920.

| Pass | Per frame | Frames | Time |
|---|---|---|---|
| EEVEE 960 by 540 previews, 16 samples, to lock the edit | 6 s | 1800 | 3 hours |
| EEVEE 4K finals, 16 samples | 53 s | 1800 | 26.5 hours |
| Cycles 4K stills for holds and the poster frame, 16 samples | 725 s | about 5 | 1 hour |
| EEVEE vertical 1080 by 1920 reframes, 16 samples | about 15 s, scaled from 4K by pixel count | 1800 | 7.5 hours |
| Remotion type layer and edit at 4K | 2.3 s | 1800 | 70 minutes |
| Remotion vertical edit | under 1 s, scaled from 4K | 1800 | 30 minutes |

That is about 40 hours of rendering, five overnight runs of 8 hours, with every pass on a shared machine. Shots where the action sits in the middle of the frame can be cropped from the 4K master to 1215 by 2160 and scaled to 1080 by 1920 with no new render, and cropping every shot brings the total to about 32 hours. Rendering the finals one shot at a time with nothing else running moves EEVEE toward its best case of 36 seconds a frame, about 18 hours for the finals. Rendering the whole film in Cycles would take about 15 days on this machine, so Cycles stays limited to stills.

Disk. A 4K PNG frame is about 6 MB, so the whole film as frames would need about 11 GB, more than the machine has free. Each shot renders into `video/out/frames/`, encodes to an H.264 intermediate at CRF 12 (about 20 to 60 MB a shot), and its frames are deleted before the next shot starts. The largest shot, about 300 frames, needs about 2 GB while it renders. The intermediates for the whole film take about 0.5 GB, and the masters take about 300 MB for 4K and 60 MB for the vertical cut. With about 6 GB free, the run keeps more than 3 GB free throughout.

## Consequences

- `video/scenes/` holds the reusable SO-101 model, cables, studio, shot format and test shot. Every film shot is a script beside them that reads a shot file.
- The film uses the MuJoCo Menagerie `robotstudio_so101` model that the hub recording runs (`video/hub/`) and the recorded motion in `video/data/`. Menagerie derives that model from The Robot Studio's `so101_new_calib` export, with the same STL parts, joint names and mid-range zero as the URDF this test loaded. Before the first film shot, `so101_urdf` either reads the Menagerie model or a check confirms that both give the same link poses for the recorded angles.
- The recording holds joint angles in degrees at 120 Hz, the gripper in percent and the cube's poses. A converter resamples it to 30 frames a second into the shot file format, maps gripper percent onto the joint's range closed end first as the device file does, and carries the recorded cube poses in place of the attach rule of the test.
- `video/remotion/` keeps the test scene for reference and gains the type layer and edit compositions.
- A faster or cooler machine would shorten every pass. The quality gap comes from the renderers, so the choice holds on any machine.
