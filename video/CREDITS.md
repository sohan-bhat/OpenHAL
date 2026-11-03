# Credits

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
