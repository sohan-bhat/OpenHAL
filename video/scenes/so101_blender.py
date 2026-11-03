"""Build the SO-101 arm in Blender from the official URDF and pose it by joint name.

Every link is an empty and every joint is an empty that turns about the URDF axis,
so a pose is a dictionary of the real arm's joint names in radians. Meshes are the
official STL parts, imported once each and shared between instances.

    import so101_urdf, so101_blender
    robot = so101_urdf.load()
    arm = so101_blender.build(robot, materials)
    arm.pose({"shoulder_pan": 0.3, "gripper": 1.2})
    arm.key(frame=12)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import bmesh
import bpy
import so101_cables
import so101_urdf as urdf
from mathutils import Matrix

SMOOTH_ANGLE = math.radians(32.0)


def _matrix(m: urdf.Mat4) -> Matrix:
    return Matrix([row[:] for row in m])


def _empty(name: str, parent: bpy.types.Object | None, collection: bpy.types.Collection) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.01
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def import_part_mesh(path: str, smooth_angle: float = SMOOTH_ANGLE) -> bpy.types.Mesh:
    """Import one STL part, merge duplicate vertices and smooth it up to smooth_angle."""
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=path, global_scale=1.0, forward_axis="Y", up_axis="Z")
    new = [o for o in bpy.data.objects if o not in before]
    obj = new[0]
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(mesh)
    bm.free()
    mesh.shade_smooth()
    mesh.set_sharp_from_angle(angle=smooth_angle)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return mesh


@dataclass
class Arm:
    """A built arm. links maps URDF link names to empties, joints maps joint names to empties."""

    robot: urdf.Robot
    root: bpy.types.Object
    links: dict[str, bpy.types.Object] = field(default_factory=dict)
    joints: dict[str, bpy.types.Object] = field(default_factory=dict)
    parts: list[bpy.types.Object] = field(default_factory=list)

    def pose(self, values: dict[str, float]) -> None:
        """Set joint values in radians. Joints left out keep their value."""
        for name, value in values.items():
            joint = self.robot.joint(name)
            obj = self.joints[name]
            angle = joint.clamp(value)
            obj.rotation_axis_angle = (angle, *joint.axis)

    def key(self, frame: int) -> None:
        """Keyframe every movable joint at frame."""
        for obj in self.joints.values():
            obj.keyframe_insert("rotation_axis_angle", frame=frame)

    def values(self) -> dict[str, float]:
        """Current joint values in radians."""
        return {name: obj.rotation_axis_angle[0] for name, obj in self.joints.items()}


def build(
    robot: urdf.Robot,
    materials: dict[str, bpy.types.Material],
    name: str = "so101",
    collection: bpy.types.Collection | None = None,
    smooth_angle: float = SMOOTH_ANGLE,
) -> Arm:
    """Create the arm. materials maps URDF material names (3d_printed, sts3215) to Blender materials."""
    collection = collection or bpy.context.scene.collection
    root = _empty(name, None, collection)
    arm = Arm(robot=robot, root=root)
    arm.links[robot.root] = _empty(f"{name}.{robot.root}", root, collection)
    meshes: dict[str, bpy.types.Mesh] = {}
    for joint in robot.joints:
        parent = arm.links[joint.parent]
        origin = _empty(f"{name}.{joint.name}.origin", parent, collection)
        origin.matrix_basis = _matrix(joint.origin)
        child = _empty(f"{name}.{joint.child}", origin, collection)
        if joint.kind in ("revolute", "continuous"):
            child.rotation_mode = "AXIS_ANGLE"
            child.rotation_axis_angle = (0.0, *joint.axis)
            arm.joints[joint.name] = child
        arm.links[joint.child] = child
    for link_name, visuals in robot.visuals.items():
        link = arm.links[link_name]
        for index, visual in enumerate(visuals):
            if visual.part not in meshes:
                meshes[visual.part] = import_part_mesh(str(robot.mesh_path(visual)), smooth_angle)
                meshes[visual.part].name = f"{name}.{visual.part}"
            obj = bpy.data.objects.new(f"{name}.{link_name}.{visual.part}.{index}", meshes[visual.part])
            collection.objects.link(obj)
            obj.parent = link
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.matrix_basis = _matrix(visual.origin)
            material = materials.get(visual.material)
            if material is not None and not obj.data.materials:
                obj.data.materials.append(material)
            obj["so101_part"] = visual.part
            obj["so101_material"] = visual.material
            arm.parts.append(obj)
    return arm


@dataclass
class Cable:
    """One servo cable: a Bezier curve with a round profile whose ends follow two links."""

    spec: dict
    obj: bpy.types.Object

    def key(self, poses: dict[str, urdf.Mat4], frame: int) -> None:
        """Move the cable ends to the given link poses and keyframe them."""
        p0, p1, p2, p3 = so101_cables.points(self.spec, poses)
        a, b = self.obj.data.splines[0].bezier_points
        a.co, a.handle_right, b.handle_left, b.co = p0, p1, p2, p3
        a.handle_left = [2 * p0[i] - p1[i] for i in range(3)]
        b.handle_right = [2 * p3[i] - p2[i] for i in range(3)]
        for point in (a, b):
            point.keyframe_insert("co", frame=frame)
            point.keyframe_insert("handle_left", frame=frame)
            point.keyframe_insert("handle_right", frame=frame)


def add_cables(
    material: bpy.types.Material, name: str = "so101", collection: bpy.types.Collection | None = None
) -> list[Cable]:
    """Create one curve per cable in cables.json."""
    collection = collection or bpy.context.scene.collection
    out = []
    for spec in so101_cables.load():
        curve = bpy.data.curves.new(f"{name}.cable.{spec['name']}", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 24
        curve.bevel_depth = spec["radius"]
        curve.bevel_resolution = 3
        curve.use_fill_caps = True
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(1)
        for point in spline.bezier_points:
            point.handle_left_type = "FREE"
            point.handle_right_type = "FREE"
        curve.materials.append(material)
        obj = bpy.data.objects.new(curve.name, curve)
        collection.objects.link(obj)
        out.append(Cable(spec=spec, obj=obj))
    return out
