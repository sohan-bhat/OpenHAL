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
