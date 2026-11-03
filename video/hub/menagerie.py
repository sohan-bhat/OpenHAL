"""Fetch the SO-101 model from MuJoCo Menagerie at a pinned commit, and check every file's hash.

The model is Apache-2.0 (video/CREDITS.md). The repository keeps only the film scene, so the
meshes are fetched once into a cache folder and checked against the hashes below.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import httpx

COMMIT = "3abca2e302625cec9429c49806121ea2855cef81"
FOLDER = "robotstudio_so101"
BASE = f"https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/{COMMIT}/{FOLDER}"
FILES = {
    "so101.xml": "982c02c027ec0c62d3459d0a6eb00dfb7dc13a451992e72ce99addc71f209805",
    "LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    "assets/base_motor_holder_so101_v1.stl": "8cd2f241037ea377af1191fffe0dd9d9006beea6dcc48543660ed41647072424",
    "assets/base_so101_v2.stl": "bb12b7026575e1f70ccc7240051f9d943553bf34e5128537de6cd86fae33924d",
    "assets/motor_holder_so101_base_v1.stl": "31242ae6fb59d8b15c66617b88ad8e9bded62d57c35d11c0c43a70d2f4caa95b",
    "assets/motor_holder_so101_wrist_v1.stl": "887f92e6013cb64ea3a1ab8675e92da1e0beacfd5e001f972523540545e08011",
    "assets/moving_jaw_so101_gripper_part0_v1.stl": (
        "3a92e115d1934d4c45cff808c4eff2ea10361a137a7f89940033a1f8a821b88c"
    ),
    "assets/moving_jaw_so101_gripper_part1_v1.stl": (
        "d10f6c671d26f62988ec95efee9370a0657b5833b3c5f8aad59fd69a87ef2aee"
    ),
    "assets/moving_jaw_so101_gripper_v1.stl": "e8a5dc040b98e27453a5b74f9087d1dbca14589cf9a17c4de7868d5ab98413cd",
    "assets/moving_jaw_so101_v1.stl": "785a9dded2f474bc1d869e0d3dae398a3dcd9c0c345640040472210d2861fa9d",
    "assets/rotation_pitch_so101_v1.stl": "9be900cc2a2bf718102841ef82ef8d2873842427648092c8ed2ca1e2ef4ffa34",
    "assets/sts3215_03a_no_horn_v1.stl": "75ef3781b752e4065891aea855e34dc161a38a549549cd0970cedd07eae6f887",
    "assets/sts3215_03a_v1.stl": "a37c871fb502483ab96c256baf457d36f2e97afc9205313d9c5ab275ef941cd0",
    "assets/under_arm_so101_v1.stl": "d01d1f2de365651dcad9d6669e94ff87ff7652b5bb2d10752a66a456a86dbc71",
    "assets/upper_arm_so101_v1.stl": "475056e03a17e71919b82fd88ab9a0b898ab50164f2a7943652a6b2941bb2d4f",
    "assets/waveshare_mounting_plate_so101_v2.stl": "e197e24005a07d01bbc06a8c42311664eaeda415bf859f68fa247884d0f1a6e9",
    "assets/wrist_roll_follower_so101_camera_mount.stl": (
        "58c457b33a26d9c9bb337aa351173e7123f84719a93f486541adef6eba57ae21"
    ),
    "assets/wrist_roll_follower_so101_gripper_part0_v1.stl": (
        "370eb470a6ab48b08febcaeb5274d2bcc91246692532ce12c795fb82977def72"
    ),
    "assets/wrist_roll_follower_so101_gripper_v1.stl": (
        "65f32debcf265420c0160afe004f8befc5df4b3e578fd59ebaa62eade0371224"
    ),
    "assets/wrist_roll_follower_so101_v1.stl": "4b17b410a12d64ec39554abc3e8054d8a97384b2dc4a8d95a5ecb2a93670f5f4",
    "assets/wrist_roll_pitch_so101_v2.stl": "6c7ec5525b4d8b9e397a30ab4bb0037156a5d5f38a4adf2c7d943d6c56eda5ae",
}
SCENE = Path(__file__).with_name("scene.xml")
SCENE_NAME = "openhal-film-scene.xml"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(cache: Path) -> Path:
    """The model folder in `cache`, fetched where a file is missing or its hash is wrong."""
    folder = cache / f"menagerie-{COMMIT[:12]}" / FOLDER
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for name, digest in FILES.items():
            target = folder / name
            if target.is_file() and _digest(target) == digest:
                continue
            response = client.get(f"{BASE}/{name}")
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != digest:
                raise RuntimeError(f"{name} from Menagerie {COMMIT[:12]} doesn't match its pinned hash.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
    return folder


def scene(cache: Path) -> Path:
    """The film scene, placed next to so101.xml so its include and the mesh folder resolve."""
    folder = fetch(cache)
    target = folder / SCENE_NAME
    shutil.copyfile(SCENE, target)
    return target
