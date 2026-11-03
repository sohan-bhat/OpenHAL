# Credits

Everything in the launch film is drawn from code. These are the outside files the code reads. None of them are stored in this repository. `video/scenes/fetch_assets.py` downloads each one at a pinned version into `video/assets/` and checks its SHA-256 against `video/assets.json`.

## SO-101 robot arm

The arm is the SO-101 by TheRobotStudio, the arm Hugging Face LeRobot uses.

| | |
|---|---|
| Source | https://github.com/TheRobotStudio/SO-ARM100, folder `Simulation/SO101`, at commit `5f6d2b876a53a4872e405b991dd925556c9e38a4` (2026-09-23) |
| License | Apache License 2.0, read from the repository's `LICENSE` file at that commit and from the GitHub license field. The fetch script keeps a copy at `video/assets/so101/LICENSE`. |
| Origin | TheRobotStudio generated the URDF from its Onshape CAD with onshape-to-robot. |
| Changes | None to the files. The film scenes import the parts as they are. `video/scenes/export_glb.py` derives smoothed GLB copies of the same parts for the Remotion project, kept only in `video/assets/so101/glb/`. |

The film uses these files.

| File | Role |
|---|---|
| `so101_new_calib.urdf` | Links, joints, limits and part placement. Joint zero sits mid-range ("new calibration"). |
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

This export has the most faithful geometry. The MuJoCo Menagerie model `robotstudio_so101` (Apache-2.0) is derived from it, according to the Menagerie README, and uses the same STL parts. The Menagerie copy adds collision primitives and a camera mount for simulation, which a film doesn't need.

The servo cables are not part of the CAD. `video/scenes/so101_cables.py` adds them as curves between servo housings.

## Studio HDRI

| | |
|---|---|
| Asset | Studio Small 09 by Sergej Majboroda, Poly Haven, 2K Radiance HDR (`studio_small_09_2k.hdr`) |
| Source | https://polyhaven.com/a/studio_small_09 |
| License | CC0 1.0. Poly Haven publishes every asset under CC0. |
| Use | Reflections and soft ambient light only. Camera rays skip it, so it never shows in frame. |

## Fonts

IBM Plex Sans and IBM Plex Mono, under the SIL Open Font License 1.1, from `design/fonts/` in this repository. See `design/README.md`.
