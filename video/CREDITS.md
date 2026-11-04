# Credits

## SO-101 arm model

The simulated arm in the film's recording is the SO-101 model from MuJoCo Menagerie, used as published, with the film scene in `video/hub/scene.xml` around it.

| | |
|---|---|
| Model | `robotstudio_so101` in MuJoCo Menagerie |
| Source | https://github.com/google-deepmind/mujoco_menagerie/tree/3abca2e302625cec9429c49806121ea2855cef81/robotstudio_so101 |
| Commit | `3abca2e302625cec9429c49806121ea2855cef81`, 2026-09-28 |
| License | Apache License 2.0, in the model's own `LICENSE` file |
| Derived from | `so101_new_calib.xml` in The Robot Studio's SO-ARM100 repository, https://github.com/TheRobotStudio/SO-ARM100 (Apache License 2.0) |
| Fetched by | `video/hub/menagerie.py`, which checks each file against a pinned SHA-256 |

The meshes stay out of this repository. The recording fetches them into a cache folder.

Joint names match the real arm in LeRobot, `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll` and `gripper`. In this model each joint's zero is the middle of its range, which The Robot Studio calls the new calibration. LeRobot's degrees also count from the middle of each joint's calibrated range, so the angles line up when a real arm's calibrated range matches the model's. LeRobot reads the gripper from 0, fully closed, to 100, fully open. The model's gripper is an angle, so the device file maps 0 to 100 percent onto the joint's range, closed end first.

## Physics

MuJoCo, https://github.com/google-deepmind/mujoco, Apache License 2.0, through the official `mujoco` Python package.

## SO-101 render model for the stack test

The render stack test (ADR 0022) draws the arm from The Robot Studio's own URDF export and STL parts, used as published. None of the files are stored in this repository.

| | |
|---|---|
| Model | `so101_new_calib.urdf` and its STL parts in The Robot Studio's SO-ARM100 repository, folder `Simulation/SO101` |
| Source | https://github.com/TheRobotStudio/SO-ARM100/tree/5f6d2b876a53a4872e405b991dd925556c9e38a4/Simulation/SO101 |
| Commit | `5f6d2b876a53a4872e405b991dd925556c9e38a4`, 2026-09-23 |
| License | Apache License 2.0, in the repository's `LICENSE` file at that commit |
| Derived from | The Robot Studio's Onshape CAD, exported with onshape-to-robot |
| Fetched by | `video/scenes/fetch_assets.py`, which checks each file against a pinned SHA-256 in `video/assets.json` and keeps a copy of the license at `video/assets/so101/LICENSE` |

`video/scenes/export_glb.py` derives smoothed GLB copies of the same parts for the Remotion project, kept only in `video/assets/so101/glb/`. The servo cables are not part of the CAD. `video/scenes/so101_cables.py` adds them as curves between servo housings.

| File | Role |
|---|---|
| `so101_new_calib.urdf` | Links, joints, limits and part placement, with joint zero mid-range (the new calibration) |
| `assets/base_so101_v2.stl` | Base |
| `assets/base_motor_holder_so101_v1.stl` | Base motor holder |
| `assets/waveshare_mounting_plate_so101_v2.stl` | Driver board plate |
| `assets/motor_holder_so101_base_v1.stl` | Shoulder motor holder |
| `assets/rotation_pitch_so101_v1.stl` | Shoulder bracket |
| `assets/upper_arm_so101_v1.stl` | Upper arm |
| `assets/under_arm_so101_v1.stl` | Lower arm |
| `assets/motor_holder_so101_wrist_v1.stl` | Wrist motor holder |
| `assets/wrist_roll_pitch_so101_v2.stl` | Wrist |
| `assets/wrist_roll_follower_so101_v1.stl` | Gripper body and fixed jaw |
| `assets/moving_jaw_so101_v1.stl` | Moving jaw |
| `assets/sts3215_03a_v1.stl` | STS3215 servo, five instances |
| `assets/sts3215_03a_no_horn_v1.stl` | STS3215 servo without horn, wrist roll |

The MuJoCo Menagerie model `robotstudio_so101` is derived from this export, according to the Menagerie README, and uses the same STL parts and joint names. The Menagerie copy adds collision primitives and a camera mount for simulation.

## Studio HDRI

| | |
|---|---|
| Model | Studio Small 09 by Sergej Majboroda, 2K Radiance HDR, `studio_small_09_2k.hdr` |
| Source | https://polyhaven.com/a/studio_small_09 |
| License | CC0 1.0. Poly Haven publishes every asset under CC0. |
| Fetched by | `video/scenes/fetch_assets.py`, against a pinned SHA-256 in `video/assets.json` |
| Use | Reflections and soft ambient light only. Camera rays skip it, so it never shows in frame. |

## Fonts

IBM Plex Sans and IBM Plex Mono, under the SIL Open Font License 1.1, from `design/fonts/` in this repository. See `design/README.md`.

## Sound

Every sound in the film is synthesized by `video/scenes/sound.py` from the edit and the hub recording. No sample, recording or library sound is used.

## Music

The music is generated in code by `video/scenes/sound.py`, the same way as the sound effects. No track, sample or loop is downloaded, so the music needs no license.

The bed holds one soft chord per beat of the edit, a quiet pluck on a 100 BPM grid and a low tock on the cuts inside a beat. The bed sits under the effects, dips under the block, the hold, the approval and each device, stops on the STOP press and stays silent through the black after STOP.

`video/scenes/assemble.py --music <file>` replaces the generated bed with an outside track, a 48 kHz PCM WAV mixed 16 dB under the effects and muted with everything else from STOP to the end of the black after STOP. Fill in this table before a cut with an outside track ships.

| | |
|---|---|
| Track | none, the film uses the generated bed |
| Composer | |
| Source | |
| License | |
| Attribution required | |

## Model check

`video/scenes/check_model.py` fetches the Menagerie files above into a cache folder with `video/hub/menagerie.py`, checks each one against its pinned SHA-256, and compares that model with the render model. Nothing it fetches is stored in this repository.

## The demo video

The demo video, `OpenHALDemo` in `remotion/src/demo/`, is drawn in Remotion with React Three Fiber and uses no Blender. It reuses the SO-101 render model, the studio HDRI and the fonts above, and adds the items below.

### Recorded session

The arm's motion, every Claude Code line and every Inspector click come from `video/data/take-4/`, a recording of the real OpenHAL hub driving the MuJoCo Menagerie SO-101 above. `video/data/TAKE.md` describes the take, and the model rows above cover its arm.

### Simplified arm parts

`remotion/scripts/simplify-arm.mjs` derives copies of the SO-101 parts with about a third of their triangles, kept only in `video/assets/so101/glb-lite/`. The source and license are the SO-101 render model's above, The Robot Studio's parts under the Apache License 2.0.

### Desk wood texture

| | |
|---|---|
| Texture | Wood Table 001, photographed by Dimitrios Savva and processed by Rico Cilliers, diffuse at 2K and normal map at 1K, `wood_table_001_diff_2k.jpg` and `wood_table_001_nor_gl_1k.jpg` |
| Source | https://polyhaven.com/a/wood_table_001 |
| License | CC0 1.0. Poly Haven publishes every asset under CC0 |
| Fetched by | `video/scenes/fetch_assets.py`, against a pinned SHA-256 in `video/assets.json`, into `video/assets/wood/` |

### Sound and music

`video/scenes/demo_sound.py` synthesizes every sound in the demo from the edit's cue sheet, the key clicks, the tool call clicks, the servo whir from the recorded joint speeds, the low tone on LIMIT_EXCEEDED, the chime when the approved drop finishes, the STOP click and the music bed. No sample, recording or library sound is used, so the sound needs no license. The music is generated in code the same way, and no outside track is used.

| | |
|---|---|
| Track | none, the demo uses the generated bed |
| Composer | |
| Source | |
| License | |

### Software

| Package | Version | License |
|---|---|---|
| Remotion, `@remotion/cli`, `@remotion/transitions`, `@remotion/media`, `@remotion/fonts` | 4.0.540 | Remotion License, free for an individual |
| `@remotion/three` | 4.0.540 | MIT |
| three.js | 0.187.0 | MIT |
| React Three Fiber and drei | 9.8.2 and 10.7.9 | MIT |
| urdf-loader | 0.13.1 | Apache License 2.0 |
| glTF Transform and meshoptimizer | 4.5.1 and 1.3.0 | MIT |

### Redrawn interfaces

The Claude Code window and the OpenHAL Inspector are redrawn in code from the recorded session and from the Inspector screenshots in `video/data/take-4/inspector/`. The Claude Code window keeps that product's layout so the session reads as it ran. OpenHAL is not affiliated with Anthropic, and the end card says so.
