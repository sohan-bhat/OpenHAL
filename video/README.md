# Launch film

The OpenHAL launch film is drawn entirely from code. There is no stock footage, AI video or screen recording. This folder holds the scenes, the shared shot and look files, and the stack test that picked the graphics tools (ADR 0020).

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
| `remotion/` | The same shot in Remotion with React Three Fiber |
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

During the test, `pmset -g therm` reported a CPU speed limit of 26 to 29 percent, so the CPU ran well below its rated speed, and other agents' builds shared the machine. The times in ADR 0020 are what the machine gave under those conditions.

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
