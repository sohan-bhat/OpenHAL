# Launch film and demo video

The OpenHAL launch film and the demo video are drawn entirely from code. There is no stock footage, AI video or screen recording. This folder holds the scenes, the shared shot and look files, the stack test that picked the graphics tools (ADR 0022), and the demo video described in [The demo video](#the-demo-video).

## Layout

| Path | What it holds |
|---|---|
| `assets.json` | Pinned URLs and SHA-256 hashes of the outside files (see CREDITS.md) |
| `scenes/fetch_assets.py` | Downloads them into `assets/`, which git ignores |
| `scenes/so101_urdf.py` | Parses the SO-101 URDF and computes link poses by joint name, pure Python |
| `scenes/so101_ik.py` | Places the gripper for hand-keyed test shots |
| `scenes/so101_blender.py` | Builds and poses the arm in Blender, cables included |
| `scenes/so101_cables.py`, `scenes/cables.json` | Servo cable ends in link frames, read by both stacks |
| `scenes/export_glb.py` | Writes smoothed GLB copies of the STL parts for Remotion |
| `scenes/look.json` | Palette, materials, desk, backdrop and lights, read by both stacks |
| `scenes/shot.py`, `scenes/shots/*.json` | Shot files with joint, camera and prop keys, read by both stacks |
| `scenes/studio_blender.py` | Materials, desk, lights, camera and render settings in Blender |
| `scenes/test_shot.py` | The stack test shot, built and rendered headless |
| `scenes/recording.py` | Reads the hub recording in `data/` and samples it at any time on its clock |
| `scenes/check_model.py` | Compares the URDF render model with the Menagerie model the recording ran |
| `scenes/film.json` | The film plan, with the set's layout, every shot's beat, span, speed and cameras, the labels and the storyboard stills |
| `scenes/convert_recording.py`, `scenes/shots/film/` | Writes one shot file per shot and `edit.json` from the plan and the recording |
| `scenes/film_props.py` | The set in Blender, with the agent's display, the layer, the cables, the phone, the bin, the workspace box and the three devices |
| `scenes/film_shot.py` | Builds one film shot in Blender from its shot file and renders it |
| `scenes/render_film.py` | Renders every shot one at a time, encodes it and deletes its frames |
| `scenes/sound.py` | Synthesizes the film's sound from the edit and the recording |
| `scenes/assemble.py` | Cuts the film in Remotion, sets the sound to -14 LUFS and muxes it, or renders the storyboard |
| `remotion/` | The test shot in Remotion with React Three Fiber, and the film's edit, labels and end card in `src/film/` |
| `data/take-4/`, `data/TAKE.md`, `data/STATS.md` | The recorded session the demo video uses, and the two measured numbers on its stat cards |
| `scenes/demo_take.py`, `scenes/demo_lines.py` | Read a take, sample the arm on the hub's clock, and lay out Claude Code's lines |
| `scenes/demo_edit.py` | Cuts the demo from the take into `remotion/src/demo/edit.json` and the sound's `cues.json` |
| `scenes/demo_sound.py` | Synthesizes the demo's sound from `cues.json` and sets it to -14 LUFS |
| `remotion/src/demo/` | The demo's composition `OpenHALDemo`, one `Scene-<id>` composition per scene, and `DemoThumbnail` |
| `remotion/scripts/simplify-arm.mjs` | Writes the arm's parts with fewer triangles for the demo into `assets/so101/glb-lite/` |
| `REFERENCE.md`, `TOOLS.md`, `PERF.md`, `YOUTUBE.md` | The series style the demo follows, the tools, the render times and the upload text |
| `out/` | Renders, which git ignores |

Every file uses the real arm's joint names, `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll` and `gripper`, in radians in code and degrees in shot files. Joint zero is the middle of each joint's range, the URDF's "new calibration". The test motion in `shots/test_pick.json` is hand-keyed by inverse kinematics. It is not hub data. The film's motion will come from a recording of the OpenHAL hub, written into the same shot format.

This poses the arm in another Blender shot.

```python
import so101_urdf, so101_blender, studio_blender
robot = so101_urdf.load()
mats = studio_blender.materials(studio_blender.load_look())
arm = so101_blender.build(robot, mats)
cables = so101_blender.add_cables(mats["cable"])
arm.pose({"shoulder_pan": 0.3, "elbow_flex": -0.2, "gripper": 0.5})
arm.key(frame=1)
```

## The demo video

The demo video shows Claude Code driving the simulated SO-101 through the OpenHAL hub, in the style of the Oopsy, Taro and Wobbl videos that REFERENCE.md describes. Remotion draws every frame, the desk scenes with React Three Fiber, and no Blender runs. The video follows the take's own order, the pick, the drop held for a person and approved in the Inspector, the request at 120 deg/s that the hub blocks with LIMIT_EXCEEDED, and STOP during a move.

### What comes from the take

- Every prompt, Claude message and tool call in the terminal is quoted from `data/take-4/claude.stream.jsonl`. A tool call reads the way Claude Code prints an MCP call, and a long call or result ends in an ellipsis where Claude Code shortens one.
- The terminal keeps the session's whole history, so earlier lines scroll up as new ones arrive. Claude's closing message of the first turn is left out, because Claude wrote that message after a check made before the Approve click, and beside the drop the video has just shown the message would read as the current state.
- Where the edit skips a wait, Claude Code's working line stays up and its timer runs over the real seconds that passed, counted from the moment the person sent the prompt. The first timer shows the 15 s Claude Code took to start.
- Every joint angle, gripper opening and cube pose is sampled from `frames.csv.gz` at 1x on the hub's clock, each frame at its simulated time plus its `lag_ms`, so the arm lines up with the clicks and the hub's messages. The joint speed on the panel is measured in simulated time.
- The pick plays in two shots. Between them the edit skips 1.35 s in which the arm holds still at the cube before the gripper closes, and the second shot opens from a new camera angle.
- The Approve and STOP clicks land on the frames of their recorded clicks, and the Inspector is redrawn from the screenshots in `data/take-4/inspector/`.
- The terminal and the Inspector are shown pushed in, 1.3 and 1.54 times, so their lines read on a phone. When Claude's long reply to the block arrives, the terminal scrolls back to the reply's first lines, where LIMIT_EXCEEDED is.
- The panel's verdicts, "done", LIMIT_EXCEEDED and "stopped", appear on the frame of the hub message or audit entry that carries them.
- The stat cards show the two numbers in `data/STATS.md`, and the device cards name three real example device files.

### Rebuild the demo

```sh
python3 -I video/scenes/fetch_assets.py
cd video/remotion && pnpm install && cd ../..
RATIO=0.35 ERROR=0.001 node video/remotion/scripts/simplify-arm.mjs
.venv/bin/python video/scenes/demo_edit.py --take take-4
.venv/bin/python video/scenes/demo_sound.py --cues video/remotion/src/demo/cues.json --out video/out/demo/sound/mix-raw.wav --normalize video/assets/demo/mix.wav
cd video/remotion
pnpm exec remotion bundle --out-dir=../out/demo/bundle --public-dir=../assets
pnpm exec remotion render ../out/demo/bundle OpenHALDemo ../out/openhal-demo-1440p.mp4 --scale=2 --concurrency=2 --gl=angle --crf=18
```

PERF.md lists the scene by scene renders and the settings of each output.

## The launch film

The film rebuilds from the recording in `data/` and the plan in `scenes/film.json`, in four steps.

1. `convert_recording.py` writes one shot file per shot and `shots/film/edit.json`.
2. `render_film.py` renders each shot in Blender with EEVEE and encodes it, landscape or vertical.
3. `assemble.py` cuts both aspect ratios in Remotion, sets the sound to -14 LUFS and muxes it.
4. `render_film.py --stills` and `assemble.py --stills` render the storyboard, one still per beat.

### What comes from the recording

Every joint angle, gripper opening and cube pose on screen is the recorded one. Frame f of a shot shows recording time `t_start + (f - 1) / 30 * speed`, with one speed for the whole shot, and the converter samples the 120 Hz rows there with linear interpolation. The gripper comes from its recorded percent, mapped onto the joint's range with the closed end first. The cube is read one physics step later than the joints, because MuJoCo fills body poses before it integrates a step. The converter checks every key it writes against the recording.

The set follows the hub's messages on the same clock. A request leaves the agent's display as a pulse on the frame the agent sent it. A request the hub passes runs along the layer and down the arm's cable. One the hub blocks stops at the layer and turns red. One held for a person stays at the layer until the hub's confirm event. STOP flashes the layer and runs to every device, the phone shows each step the person takes, and each device lights on its connect event. Each label appears on the frame of the message that triggers it.

Each shot plays one span of the recording at one speed. Rows are the 120 Hz rows of each beat file, counted from 0.

| Shot | Beat on screen | On screen | Recording | Speed | Rows used |
|---|---|---|---|---|---|
| `s1-reveal` | Cold open | 3.00 s | 1.02 to 3.99 s | 1.0x | `beat-1-devices.json` 1 to 357 |
| `s1-servo` | Cold open | 1.30 s | 4.02 to 5.29 s | 1.0x | `beat-1-devices.json` 361 to 513 |
| `s1-cable` | Cold open | 1.30 s | 5.32 to 6.59 s | 1.0x | `beat-1-devices.json` 517 to 669 |
| `s1-gripper` | Cold open | 1.60 s | 6.62 to 8.19 s | 1.0x | `beat-1-devices.json` 673 to 861 |
| `s2-sides` | The two sides | 6.00 s | 8.20 to 10.94 s | 0.46x | `beat-1-devices.json` 863 to 1180, `beat-2-pick-and-place.json` 0 to 10 |
| `s3-request` | Agent to arm | 1.60 s | 10.95 to 12.52 s | 1.0x | `beat-2-pick-and-place.json` 12 to 199 |
| `s3-pick` | Agent to arm | 5.20 s | 12.55 to 17.72 s | 1.0x | `beat-2-pick-and-place.json` 204 to 823 |
| `s4-limit` | The limit | 3.53 s | 17.90 to 21.40 s | 1.0x | `beat-2-pick-and-place.json` 846 to 910, `beat-3-limit.json` 0 to 354 |
| `s5-hold` | Held for a person | 3.20 s | 23.15 to 26.32 s | 1.0x | `beat-4-approval.json` 196 to 575 |
| `s5-drop` | Held for a person | 3.00 s | 26.35 to 29.32 s | 1.0x | `beat-4-approval.json` 580 to 935 |
| `s6-stop` | One STOP | 3.00 s | 31.00 to 33.97 s | 1.0x | `beat-4-approval.json` 1138 to 1171, `beat-5-stop.json` 0 to 321 |
| black | after STOP | 0.60 s | | | |
| `s7-devices` | Any hardware | 6.40 s | 1.02 to 8.98 s | 1.25x | `beat-1-devices.json` 1 to 956 |
| `s8-end` | End card | 6.50 s | | | |
| | | 46.23 s in all | | | |

The cold open and the devices shot both use the first beat's opening seconds, where the arm stands still. The two sides shot plays the end of that beat at 0.46 times and the devices shot plays its start at 1.25 times, with the arm still in both. The limit shot opens in the last quiet second of the pick and place beat, so the workspace box draws in before the request. Within the limit shot the arm moves 0.00 degrees, and after the arm's safe state in the STOP shot it moves at most 0.0101 degrees.

### The render model

The render loader keeps The Robot Studio's URDF. `check_model.py` loads the Menagerie model the recording ran and compares the two.

```
ok    bodies: 7 bodies in 4269 recorded frames, at most 0.0013 mm and 0.0008 deg apart
ok    meshes: 102 mesh placements at 6 poses, bounds and centroids at most 0.0017 mm apart, Menagerie only: camera_mount (wrist_roll_follower_so101_camera_mount)
ok    recording: recorded gripper body within 0.1183 mm of the URDF pose one physics step earlier
```

The tolerance is 0.01 mm and 0.01 degrees for the models and 0.2 mm for the recorded pose, which is rounded to 0.01 mm. The Menagerie model adds a camera mount on the wrist, a visual part with no collision, which the render leaves out. Menagerie's `gripperframe` site sits about 20 mm from the URDF's `gripper_frame_link`, so the workspace box is drawn from the device file in the arm's base frame and never from the URDF tip.

```sh
uv run --extra mujoco python video/scenes/check_model.py --cache video/assets/menagerie
```

### The layer and the type

The OpenHAL layer is light in the scene, drawn in Blender. A pink hairline lies on the desk between the agent's side and the hardware, a faint sheet of light rises from it, and each cable ends in a port on it. ADR 0022 planned the layer as flat graphics in Remotion. In the scene it takes the shot's depth of field, reflections and motion blur, and the arm passes in front of it. Remotion sets every word on screen, the code labels in IBM Plex Mono, the small wordmark in the two sides shot and the end card.

### Sound

`sound.py` synthesizes every sound from the edit and the recording. Each joint is a servo voice whose pitch and level follow its speed on screen. A request clicks, the block is a low tone, the hold and the approval chime, each device plucks on its connect event, and the mix cuts to silence from STOP to the end of the black. `assemble.py` measures the mix and normalizes it in two linear loudnorm passes. The music slot is described in CREDITS.md.

### Rebuild the film

```sh
python3 -I video/scenes/fetch_assets.py
python3 -I video/scenes/convert_recording.py
python3 -I video/scenes/render_film.py --aspect landscape --width 960 --height 540 --samples 8
python3 -I video/scenes/render_film.py --aspect vertical --width 960 --height 540 --samples 8
python3 -I video/scenes/render_film.py --stills --width 1920 --height 1080 --samples 64
cd video/remotion && pnpm install && cd ../..
uv run python video/scenes/assemble.py --scale 0.25
uv run python video/scenes/assemble.py --stills
```

`render_film.py` takes the landscape size and swaps it for vertical. Shot videos go to `video/out/public/shots/`, the folder Remotion serves, and the previews and storyboard to `video/out/preview/`.

### Preview renders

`video/out/preview/` holds the rough preview for review, EEVEE at 8 samples.

| File | What it is |
|---|---|
| `openhal-film-landscape-960x540.mp4` | The whole film at 960 by 540, with labels, end card and the first sound pass |
| `openhal-film-vertical-540x960.mp4` | The vertical cut at 540 by 960, each shot reframed in the 3D scene |
| `storyboard-1-1920x1080.png` to `storyboard-8-1920x1080.png` | One still per beat at 1920 by 1080, EEVEE at 64 samples with the beat's label, and the end card |

### Render plan for the 4K master and the vertical cut

`render_film.py --measure` rendered frames 10 and 30 of three landscape shots and two vertical shots at full size with nothing else rendering, on 2026-11-03, with macOS holding the CPU at 29 percent of its rated speed. The film has 1387 frames, of which 1174 are Blender frames in each aspect ratio. The black after STOP and the end card come from Remotion alone.

| Pass | Measured per frame | Frames | Time |
|---|---|---|---|
| EEVEE 3840 by 2160, 16 samples | 26.9 to 37.8 s, mean 30.3 s | 1174 | 9.9 hours |
| EEVEE 2160 by 3840, 16 samples | 24.2 to 30.5 s, mean 27.4 s | 1174 | 8.9 hours |
| Scene build and shader compile | about 8 s a shot | 24 shots | 3 minutes |
| Cycles 4K stills for the storyboard and the thumbnail, 16 samples | 112.8 s at 1920 by 1080, about 451 s at 4K by pixel count | 8 | 1 hour |
| Remotion edit at 4K, both cuts | 0.85 s with the preview's shot videos as sources, up to about 1.5 s with 4K sources | 2774 | 40 to 70 minutes |

That is about 21 hours in all, three overnight runs, against the 27 to 33 hours ADR 0022 planned. A 4K frame takes about 30 seconds today where the stack test averaged 43 with other renders sharing the machine, and the film is 46 seconds where the plan assumed 60. The vertical cut costs more than the plan's 1080 by 1920 reframes, because 2160 by 3840 has as many pixels as the 4K master.

Disk. A 4K PNG frame is 5.5 to 6.8 MB. The largest shot, `s7-devices` with 192 frames, needs about 1.3 GB while it renders, and its frames are deleted once the shot is encoded. The H.264 intermediates come to about 0.1 GB for each cut at CRF 12, scaled from the stack test's 60 KB a frame at CRF 14, and Remotion's bundle copies them once. With the masters the run needs about 1.5 GB at its peak, so a start with 6 GB free stays well above the 2.5 GB floor `render_film.py` keeps.

```sh
python3 -I video/scenes/render_film.py --aspect landscape --width 3840 --height 2160 --samples 16 --crf 12
python3 -I video/scenes/render_film.py --aspect vertical --width 3840 --height 2160 --samples 16 --crf 12
uv run python video/scenes/assemble.py --scale 1
```

## Tools on this machine

The machine is a 2018 MacBook Pro, Intel Core i7-8750H with 6 cores, 16 GB of RAM, a Radeon Pro 555X with 4 GB and Intel UHD 630, on macOS 15.5. Nothing was installed with sudo.

| Tool | Version | Where | Source |
|---|---|---|---|
| Blender | 4.5.15 LTS, Intel build | `~/Applications/Blender-4.5.15.app` | `blender-4.5.15-macos-x64.dmg` from the ftp.nluug.nl mirror of download.blender.org, SHA-256 `3801a976…7f21ed78` checked against the release's `.sha256` file |
| ffmpeg and ffprobe | 9.0.2, static x86_64 | `~/.local/opt/ffmpeg-9.0.2/bin/` | evermeet.cx release builds |
| Node and pnpm | 22.17.1 and 10.24.0 | already installed | |
| Chrome Headless Shell | 158.0.8127.2, mac-x64 | `remotion/node_modules/.remotion/` | downloaded by Remotion on first render |

Blender 4.5 is the newest release with an Intel macOS build. The 5.0, 5.1 and 5.2 release folders hold only `macos-arm64` disk images.

Cycles can't use the Radeon Pro 555X. With the compute device set to Metal, Blender 4.5 lists only the CPU, and according to the Blender 4.5 manual, Metal rendering is supported on Apple Silicon only. Cycles runs on the six CPU cores. EEVEE and the Remotion WebGL renderer use the GPU, through Metal and through ANGLE on Metal.

During the test, `pmset -g therm` reported a CPU speed limit of 26 to 29 percent, so the CPU ran well below its rated speed, and other agents' builds shared the machine. The times in ADR 0022 are what the machine gave under those conditions.

## Rebuild the test shot

```sh
B=~/Applications/Blender-4.5.15.app/Contents/MacOS/Blender
FF=~/.local/opt/ffmpeg-9.0.2/bin/ffmpeg
python3 -I video/scenes/fetch_assets.py
$B -b --factory-startup -noaudio --python video/scenes/export_glb.py
python3 -I video/scenes/author_test_pick.py
python3 -I video/scenes/so101_cables.py
```

Blender, Cycles on the CPU, three key frames at 4K (about 12 minutes each here).

```sh
$B -b --factory-startup -noaudio --python video/scenes/test_shot.py -- \
  --engine cycles --width 3840 --height 2160 --samples 16 --frames 1,94,150 --out video/out/frames/cycles-4k
```

`--frames` also takes ranges with a step, such as `1-150:15`, and every run appends each frame's render time to `times.csv` in its output folder.

Blender, EEVEE, the whole shot at 4K.

```sh
$B -b --factory-startup -noaudio --python video/scenes/test_shot.py -- \
  --engine eevee --width 3840 --height 2160 --samples 16 --frames 1-150 --out video/out/frames/eevee-4k
```

Encode a frame folder and delete the frames.

```sh
$FF -framerate 30 -i video/out/frames/eevee-4k/frame_%04d.png -c:v libx264 -preset slow -crf 14 \
  -pix_fmt yuv420p -movflags +faststart video/out/test/blender-eevee-4k.mp4
rm video/out/frames/eevee-4k/frame_*.png
```

Remotion, the whole shot at 4K, straight to H.264.

```sh
cd video/remotion
pnpm install
pnpm exec remotion render TestPick ../out/test/remotion-4k.mp4 --crf=14
pnpm exec remotion still TestPick ../out/test/remotion-4k-f094.png --frame=93 --timeout=300000
```

Remotion counts frames from 0 and the shot files count from 1, so Remotion frame 93 is shot frame 94. The longer timeout covers a still started while Blender holds the GPU.

The comparison still reads three PNG files from `video/assets/compare/` and sets the labels in IBM Plex.

```sh
mkdir -p video/assets/compare
cp video/out/test/blender-cycles-4k-f094.png video/assets/compare/cycles.png
cp video/out/test/blender-eevee-4k-f094.png video/assets/compare/eevee.png
cp video/out/test/remotion-4k-f094.png video/assets/compare/remotion.png
cd video/remotion && pnpm exec remotion still Compare ../out/test/compare-f094.png
```

## Test renders

`video/out/test/` holds the results of the stack test on this machine.

| File | What it is |
|---|---|
| `blender-eevee-4k.mp4` | EEVEE, the whole shot at 4K, 16 samples |
| `remotion-4k.mp4` | Remotion and three.js, the whole shot at 4K |
| `blender-cycles-4k-f001.png`, `-f094`, `-f150` | Cycles, three key frames at 4K, 16 samples |
| `blender-eevee-4k-f001.png`, `-f094`, `-f150` | EEVEE stills of the same frames |
| `remotion-4k-f001.png`, `-f094`, `-f150` | Remotion stills of the same frames |
| `blender-eevee-4k-32spp-f094.png` | EEVEE at 32 samples, to compare with 16 |
| `remotion-4k-f094-wider-dof-trial.png` | Remotion with a stronger depth of field blur, a trial left out of the shot |
| `compare-f094.png` | The three stacks side by side, with 100 percent crops |
