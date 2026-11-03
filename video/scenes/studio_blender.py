"""The studio for every Blender shot: materials, desk, backdrop, lights, camera and render settings.

Values come from video/scenes/look.json, which the Remotion project reads too.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

SCENES = Path(__file__).resolve().parent
ASSETS = SCENES.parent / "assets"


def load_look() -> dict[str, Any]:
    """Read look.json."""
    return json.loads((SCENES / "look.json").read_text())


def srgb_to_linear(hex_color: str) -> tuple[float, float, float, float]:
    """Convert #rrggbb to linear RGBA for Blender."""
    out = []
    for i in (1, 3, 5):
        c = int(hex_color[i : i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


def reset() -> None:
    """Empty the scene, keeping the default scene datablock."""
    for collection in (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.curves,
    ):
        for block in list(collection):
            collection.remove(block)


def _principled(name: str) -> tuple[bpy.types.Material, Any, Any]:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    return mat, nodes, bsdf


def _noise_bump(
    mat: bpy.types.Material,
    bsdf: Any,
    scale: float,
    strength: float,
    distance: float,
    bevel: float = 0.0,
    bevel_samples: int = 0,
) -> None:
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coords = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 4.0
    links.new(coords.outputs["Object"], noise.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    if bevel > 0.0 and bevel_samples > 0:
        bev = nodes.new("ShaderNodeBevel")
        bev.samples = bevel_samples
        bev.inputs["Radius"].default_value = bevel
        links.new(bev.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def materials(look: dict[str, Any], edge_bevel: int = 0) -> dict[str, bpy.types.Material]:
    """Build the physically based materials. Keys match URDF material names plus scene props.

    edge_bevel is the sample count of the Cycles bevel shader that rounds the hard CAD
    edges of the printed parts and servos. 0 leaves it out.
    """
    pal, spec = look["palette"], look["materials"]
    out: dict[str, bpy.types.Material] = {}

    mat, _, bsdf = _principled("printed_pla")
    p = spec["printed"]
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(pal["printed"])
    bsdf.inputs["Roughness"].default_value = p["roughness"]
    bsdf.inputs["Specular IOR Level"].default_value = p["specular"]
    bsdf.inputs["IOR"].default_value = 1.46
    bsdf.inputs["Subsurface Weight"].default_value = p["subsurface"]
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.9, 0.75)
    bsdf.inputs["Subsurface Scale"].default_value = 0.0015
    _noise_bump(mat, bsdf, scale=2600.0, strength=p["bump"], distance=0.0002, bevel=0.0005, bevel_samples=edge_bevel)
    out["3d_printed"] = mat

    mat, _, bsdf = _principled("servo_housing")
    s = spec["servo"]
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(pal["servo"])
    bsdf.inputs["Roughness"].default_value = s["roughness"]
    bsdf.inputs["Specular IOR Level"].default_value = s["specular"]
    _noise_bump(mat, bsdf, scale=1800.0, strength=0.02, distance=0.0002, bevel=0.0004, bevel_samples=edge_bevel)
    out["sts3215"] = mat

    mat, _, bsdf = _principled("servo_cable")
    c = spec["cable"]
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(pal["cable"])
    bsdf.inputs["Roughness"].default_value = c["roughness"]
    bsdf.inputs["Specular IOR Level"].default_value = c["specular"]
    out["cable"] = mat

    mat, nodes, bsdf = _principled("desk_linoleum")
    d = spec["desk"]
    links = mat.node_tree.links
    coords = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 6.0
    links.new(coords.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    base = srgb_to_linear(pal["desk"])
    ramp.color_ramp.elements[0].color = (*tuple(v * 0.9 for v in base[:3]), 1.0)
    ramp.color_ramp.elements[1].color = (*tuple(v * 1.1 for v in base[:3]), 1.0)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = d["roughness"] - 0.06
    rough.inputs["To Max"].default_value = d["roughness"] + 0.06
    links.new(noise.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = d["specular"]
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 900.0
    links.new(coords.outputs["Object"], fine.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.03
    bump.inputs["Distance"].default_value = 0.0002
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    out["desk"] = mat

    mat, _, bsdf = _principled("cube_paint")
    k = spec["cube"]
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(pal["cube"])
    bsdf.inputs["Roughness"].default_value = k["roughness"]
    bsdf.inputs["Specular IOR Level"].default_value = k["specular"]
    _noise_bump(mat, bsdf, scale=1400.0, strength=0.03, distance=0.0002)
    out["cube"] = mat

    mat, _, bsdf = _principled("backdrop")
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(pal["backdrop"])
    bsdf.inputs["Roughness"].default_value = 0.9
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    out["backdrop"] = mat
    return out


def _box(
    name: str, size: tuple[float, float, float], location: tuple[float, float, float], bevel: float
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0.0:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 4
        mod.limit_method = "ANGLE"
        obj.data.shade_smooth()
        obj.data.set_sharp_from_angle(angle=math.radians(40.0))
    return obj


def desk_and_backdrop(
    look: dict[str, Any], mats: dict[str, bpy.types.Material], view_from: Vector, view_to: Vector
) -> None:
    """A large linoleum desk and a dark backdrop wall square to the mean view direction."""
    sx, sy, sz = look["desk"]["size"]
    cx, cy = look["desk"]["center"]
    desk = _box("desk", (sx * 2.2, sy * 2.6, sz), (cx, cy, -sz / 2), 0.002)
    desk.data.materials.append(mats["desk"])
    direction = view_to - view_from
    direction.z = 0.0
    direction.normalize()
    center = view_to + direction * look["backdrop"]["distance"]
    height = look["backdrop"]["height"]
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(center.x, center.y, height / 2 - 0.05))
    wall = bpy.context.object
    wall.name = "backdrop"
    wall.scale = (look["backdrop"]["width"], height, 1.0)
    wall.rotation_euler = (math.radians(90.0), 0.0, math.atan2(direction.y, direction.x) + math.radians(90.0))
    wall.data.materials.append(mats["backdrop"])


def _aim(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def lights(look: dict[str, Any], power: dict[str, float]) -> dict[str, bpy.types.Object]:
    """Soft area lights from look.json. power maps light names to watts."""
    out = {}
    for name, spec in look["lights"].items():
        data = bpy.data.lights.new(name, "AREA")
        data.shape = "RECTANGLE"
        data.size, data.size_y = spec["size"]
        data.energy = power.get(name, 0.0)
        data.color = srgb_to_linear(spec["color"])[:3]
        if "spread_deg" in spec:
            data.spread = math.radians(spec["spread_deg"])
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = spec["position"]
        _aim(obj, Vector(spec["target"]))
        out[name] = obj
    return out


def world(look: dict[str, Any]) -> None:
    """HDRI for reflections and soft ambient light, hidden from the camera."""
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("world")
    w = scene.world
    w.use_nodes = True
    nodes, links = w.node_tree.nodes, w.node_tree.links
    nodes.clear()
    coords = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(look["hdri"]["rotation_deg"]))
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(ASSETS / look["hdri"]["file"]), check_existing=True)
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = look["hdri"]["strength"]
    dark = nodes.new("ShaderNodeBackground")
    dark.inputs["Color"].default_value = srgb_to_linear(look["palette"]["backdrop"])
    path = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    output = nodes.new("ShaderNodeOutputWorld")
    links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    links.new(bg.outputs["Background"], mix.inputs[1])
    links.new(dark.outputs["Background"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])


def camera() -> bpy.types.Object:
    """A full-frame camera with depth of field."""
    data = bpy.data.cameras.new("camera")
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.dof.use_dof = True
    data.dof.aperture_blades = 0
    data.clip_start = 0.01
    data.clip_end = 20.0
    obj = bpy.data.objects.new("camera", data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj
    return obj


def key_camera(obj: bpy.types.Object, cam: dict[str, Any], frame: int) -> None:
    """Place and keyframe the camera from a shot.camera_at() result."""
    obj.location = cam["position"]
    _aim(obj, Vector(cam["target"]))
    forward = (Vector(cam["target"]) - Vector(cam["position"])).normalized()
    obj.data.lens = cam["lens_mm"]
    obj.data.sensor_width = cam["sensor_mm"]
    obj.data.dof.aperture_fstop = cam["fstop"]
    obj.data.dof.focus_distance = (Vector(cam["focus"]) - Vector(cam["position"])).dot(forward)
    obj.keyframe_insert("location", frame=frame)
    obj.keyframe_insert("rotation_euler", frame=frame)
    obj.data.keyframe_insert("lens", frame=frame)
    obj.data.dof.keyframe_insert("focus_distance", frame=frame)
    obj.data.dof.keyframe_insert("aperture_fstop", frame=frame)


def render_settings(engine: str, width: int, height: int, samples: int, fps: int) -> None:
    """Cycles on the CPU or EEVEE, with motion blur, AgX color and 8-bit PNG frames."""
    scene = bpy.context.scene
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
    r.fps = fps
    r.use_motion_blur = True
    r.motion_blur_shutter = 0.5
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.image_settings.compression = 15
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0
    if engine == "cycles":
        r.engine = "CYCLES"
        c = scene.cycles
        c.device = "CPU"
        c.samples = samples
        c.use_adaptive_sampling = True
        c.adaptive_threshold = 0.03
        c.adaptive_min_samples = 0
        c.use_denoising = True
        c.denoiser = "OPENIMAGEDENOISE"
        c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        c.denoising_prefilter = "ACCURATE"
        c.max_bounces = 4
        c.diffuse_bounces = 2
        c.glossy_bounces = 2
        c.transmission_bounces = 4
        c.caustics_reflective = False
        c.caustics_refractive = False
        c.sample_clamp_indirect = 6.0
        c.use_light_tree = True
        c.use_auto_tile = True
        c.tile_size = 1024
        c.use_animated_seed = True
        r.use_persistent_data = True
    else:
        r.engine = "BLENDER_EEVEE_NEXT"
        e = scene.eevee
        e.taa_render_samples = samples
        e.use_shadows = True
        e.shadow_ray_count = 2
        e.shadow_step_count = 8
        e.use_raytracing = True
        e.ray_tracing_method = "SCREEN"
        e.ray_tracing_options.resolution_scale = "1"
        e.use_fast_gi = True
        e.use_overscan = True
        e.motion_blur_steps = 1
