"""Convert every SO-101 STL part into a GLB with smoothed normals for the Remotion project.

Blender imports each part the same way the Blender scenes do (duplicate vertices
merged, smooth shading up to the same crease angle) and writes it in the STL's own
Z-up frame to video/assets/so101/glb/<part>.glb, so both stacks shade the same
normals. Run it once after fetch_assets.py:

    Blender -b --factory-startup -noaudio --python video/scenes/export_glb.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import so101_blender
import so101_urdf as urdf


def main() -> int:
    """Export one GLB per unique mesh in the URDF."""
    robot = urdf.load()
    out = robot.directory / "glb"
    out.mkdir(parents=True, exist_ok=True)
    parts = {v.part: robot.mesh_path(v) for visuals in robot.visuals.values() for v in visuals}
    for part, path in sorted(parts.items()):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        mesh = so101_blender.import_part_mesh(str(path))
        obj = bpy.data.objects.new(part, mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.gltf(
            filepath=str(out / f"{part}.glb"),
            export_format="GLB",
            use_selection=True,
            export_yup=False,
            export_normals=True,
            export_texcoords=False,
            export_materials="NONE",
            export_apply=True,
        )
        print(f"wrote {out / part}.glb")
    return 0


if __name__ == "__main__":
    main()
