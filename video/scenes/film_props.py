"""The film set around the SO-101 in Blender, built from film.json's layout.

Every prop is plain geometry with the studio's materials: the agent's display with its
chat panel, the OpenHAL layer as a pink hairline on the desk with a faint sheet of light
above it, the cables that join each side to the layer, the request pulses, the phone,
the bin, the workspace box and the three devices from the recording's first beat.

Anything that changes over a shot has a key() method that keys it at one frame, so
film_shot.py can drive the whole set from the recorded events frame by frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import bmesh
import bpy
import studio_blender as studio
from mathutils import Matrix, Vector

TEXT = "#eceeec"
TEXT_2 = "#afb5ad"
SURFACE = "#212220"
BORDER = "#383a36"
BLOCKED = "#d57a72"
SCREEN = (math.radians(90.0), 0.0, math.radians(90.0))
"""Turns a shape drawn in the XY plane into a display's screen plane, which faces local +x."""


def _link(obj: bpy.types.Object, collection: bpy.types.Collection | None = None) -> bpy.types.Object:
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def _mesh_object(name: str, bm: bmesh.types.BMesh, material: bpy.types.Material | None) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    if material is not None:
        mesh.materials.append(material)
    return _link(bpy.data.objects.new(name, mesh))


def _round(obj: bpy.types.Object, width: float, segments: int = 3, angle_deg: float = 40.0) -> None:
    if width <= 0.0:
        return
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle_deg)
    obj.data.shade_smooth()
    obj.data.set_sharp_from_angle(angle=math.radians(angle_deg))


def box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    material: bpy.types.Material | None,
    bevel: float = 0.0,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    """A box of the given size centered at location, in the parent's frame."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = _mesh_object(name, bm, material)
    obj.location = location
    _round(obj, bevel)
    if parent is not None:
        obj.parent = parent
    return obj


def cylinder(
    name: str,
    radius: float,
    depth: float,
    location: tuple[float, float, float],
    material: bpy.types.Material | None,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel: float = 0.0,
    parent: bpy.types.Object | None = None,
    segments: int = 40,
) -> bpy.types.Object:
    """A capped cylinder along its local z axis."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    obj = _mesh_object(name, bm, material)
    obj.location = location
    obj.rotation_euler = rotation
    _round(obj, bevel, angle_deg=50.0)
    if parent is not None:
        obj.parent = parent
    return obj


def sphere(name: str, radius: float, material: bpy.types.Material) -> bpy.types.Object:
    """A small UV sphere."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=radius)
    obj = _mesh_object(name, bm, material)
    obj.data.shade_smooth()
    return obj


def rounded_rect(
    name: str,
    width: float,
    height: float,
    radius: float,
    material: bpy.types.Material | None,
    depth: float = 0.0,
    parent: bpy.types.Object | None = None,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    origin: str = "center",
) -> bpy.types.Object:
    """A rounded rectangle in the local XY plane, extruded by depth along +z when depth > 0.

    origin "left" puts the local origin on the left edge, so scaling x grows the shape rightward.
    """
    radius = min(radius, width / 2, height / 2)
    left = 0.0 if origin == "left" else -width / 2
    points = []
    for cx, cy, a0 in (
        (left + width - radius, height / 2 - radius, 0.0),
        (left + radius, height / 2 - radius, 90.0),
        (left + radius, -height / 2 + radius, 180.0),
        (left + width - radius, -height / 2 + radius, 270.0),
    ):
        for i in range(7):
            a = math.radians(a0 + 90.0 * i / 6)
            points.append((cx + radius * math.cos(a), cy + radius * math.sin(a), 0.0))
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in points]
    face = bm.faces.new(verts)
    if depth > 0.0:
        ext = bmesh.ops.extrude_face_region(bm, geom=[face])
        moved = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=(0.0, 0.0, depth), verts=moved)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _mesh_object(name, bm, material)
    obj.location = location
    obj.rotation_euler = rotation
    if parent is not None:
        obj.parent = parent
    return obj


def _empty(name: str, location: tuple[float, float, float], yaw_deg: float = 0.0) -> bpy.types.Object:
    obj = _link(bpy.data.objects.new(name, None))
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
    return obj


@dataclass
class Glow:
    """An emission material whose strength is keyed frame by frame."""

    material: bpy.types.Material
    socket: Any
    base: float

    def key(self, level: float, frame: int) -> None:
        """Key the strength at level times the base strength."""
        self.socket.default_value = self.base * max(level, 0.0)
        self.socket.keyframe_insert("default_value", frame=frame)


def glow(name: str, color: str, strength: float, alpha_ramp: bool = False) -> Glow:
    """A pure emission material. alpha_ramp fades it out along the object's local +z for light sheets."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = studio.srgb_to_linear(color)
    emit.inputs["Strength"].default_value = strength
    if alpha_ramp:
        mat.surface_render_method = "BLENDED"
        mat.use_transparency_overlap = False
        coords = nodes.new("ShaderNodeTexCoord")
        sep = nodes.new("ShaderNodeSeparateXYZ")
        ramp = nodes.new("ShaderNodeMapRange")
        ramp.inputs["From Min"].default_value = 0.0
        ramp.inputs["From Max"].default_value = 1.0
        ramp.inputs["To Min"].default_value = 1.0
        ramp.inputs["To Max"].default_value = 0.0
        power = nodes.new("ShaderNodeMath")
        power.operation = "POWER"
        power.inputs[1].default_value = 2.2
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links.new(coords.outputs["Generated"], sep.inputs["Vector"])
        links.new(sep.outputs["Z"], ramp.inputs["Value"])
        links.new(ramp.outputs["Result"], power.inputs[0])
        links.new(power.outputs["Value"], mix.inputs["Fac"])
        links.new(transparent.outputs["BSDF"], mix.inputs[1])
        links.new(emit.outputs["Emission"], mix.inputs[2])
        links.new(mix.outputs["Shader"], out.inputs["Surface"])
    else:
        links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return Glow(material=mat, socket=emit.inputs["Strength"], base=strength)


def solid(
    name: str, color: str, roughness: float, metallic: float = 0.0, specular: float = 0.5, coat: float = 0.0
) -> bpy.types.Material:
    """A plain Principled material."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = studio.srgb_to_linear(color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Specular IOR Level"].default_value = specular
    bsdf.inputs["Coat Weight"].default_value = coat
    return mat


def no_shadow(obj: bpy.types.Object) -> None:
    """Keep a light-emitting prop from casting shadows."""
    obj.visible_shadow = False


@dataclass
class Path3:
    """A polyline sampled from a cubic Bezier, measured by arc length."""

    points: list[Vector]
    lengths: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        total = 0.0
        self.lengths = [0.0]
        for a, b in zip(self.points, self.points[1:], strict=False):
            total += (b - a).length
            self.lengths.append(total)

    @property
    def length(self) -> float:
        """Total arc length in meters."""
        return self.lengths[-1]

    def at(self, s: float) -> Vector:
        """The point at fraction s of the arc length."""
        target = min(max(s, 0.0), 1.0) * self.length
        for i in range(1, len(self.lengths)):
            if self.lengths[i] >= target:
                span = self.lengths[i] - self.lengths[i - 1] or 1.0
                f = (target - self.lengths[i - 1]) / span
                return self.points[i - 1].lerp(self.points[i], f)
        return self.points[-1].copy()


def bezier_points(p0: Vector, p1: Vector, p2: Vector, p3: Vector, steps: int = 48) -> list[Vector]:
    """Sample a cubic Bezier."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        out.append(p0 * (u * u * u) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * (t * t * t))
    return out


@dataclass
class Cable:
    """A cable lying on the desk between a device and its port on the layer.

    The trail is a slightly thicker copy of the curve in the light's material. Keying its
    bevel factors draws only a short span of it, so a streak of light runs along the cable.
    """

    name: str
    path: Path3
    obj: bpy.types.Object
    trail: bpy.types.Object
    light: Glow

    def key_drawn(self, fraction: float, frame: int) -> None:
        """Key how much of the cable is laid out from its start, 0 to 1."""
        self.obj.data.bevel_factor_end = min(max(fraction, 0.0), 1.0)
        self.obj.data.keyframe_insert("bevel_factor_end", frame=frame)

    def key_trail(self, head: float | None, length: float, frame: int) -> None:
        """Key the lit span ending at fraction head of the cable, or no span for None."""
        data = self.trail.data
        if head is None:
            data.bevel_factor_start, data.bevel_factor_end = 0.0, 0.0
        else:
            data.bevel_factor_start = min(max(head - length, 0.0), 1.0)
            data.bevel_factor_end = min(max(head, 0.0), 1.0)
        data.keyframe_insert("bevel_factor_start", frame=frame)
        data.keyframe_insert("bevel_factor_end", frame=frame)


def _curve(name: str, points: tuple[Vector, Vector, Vector, Vector], radius: float) -> bpy.types.Curve:
    a, b, c, d = points
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 32
    curve.bevel_depth = radius
    curve.bevel_resolution = 4
    curve.use_fill_caps = True
    curve.bevel_factor_mapping_start = "SPLINE"
    curve.bevel_factor_mapping_end = "SPLINE"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(1)
    p, q = spline.bezier_points
    p.co, p.handle_right, q.handle_left, q.co = a, b, c, d
    p.handle_left = a * 2 - b
    q.handle_right = d * 2 - c
    return curve


def desk_cable(
    name: str, start: Vector, end: Vector, radius: float, material: bpy.types.Material, light: Glow
) -> Cable:
    """A cable from start to end on the desk, leaving and entering square to the layer line."""
    a = Vector((start.x, start.y, radius))
    d = Vector((end.x, end.y, radius))
    span = (d - a).length
    b = a + Vector((0.0, math.copysign(span * 0.45, d.y - a.y), 0.0))
    c = d - Vector((0.0, math.copysign(span * 0.35, d.y - a.y), 0.0))
    curve = _curve(name, (a, b, c, d), radius)
    curve.materials.append(material)
    obj = _link(bpy.data.objects.new(name, curve))
    lit = _curve(f"{name}.trail", (a, b, c, d), radius * 1.18)
    lit.materials.append(light.material)
    trail = _link(bpy.data.objects.new(f"{name}.trail", lit))
    no_shadow(trail)
    lit.bevel_factor_end = 0.0
    return Cable(name=name, path=Path3(bezier_points(a, b, c, d)), obj=obj, trail=trail, light=light)


@dataclass
class Layer:
    """The OpenHAL layer: a hairline on the desk, a faint sheet of light above it, and one port per cable."""

    line: bpy.types.Object
    line_glow: Glow
    sheet: bpy.types.Object
    sheet_glow: Glow
    y: float
    x0: float
    x1: float
    ports: dict[str, tuple[bpy.types.Object, Glow]] = field(default_factory=dict)

    def key_draw(self, progress: float, frame: int) -> None:
        """Key how far the line has drawn out from its middle, 0 to 1."""
        s = max(progress, 1e-4)
        for obj in (self.line, self.sheet):
            obj.scale = (s, 1.0, 1.0)
            obj.keyframe_insert("scale", frame=frame)

    def port_point(self, name: str) -> Vector:
        """World position of a port, at the hairline's height."""
        return self.ports[name][0].location.copy()


def build_layer(spec: dict[str, Any], accent: str) -> Layer:
    """The hairline, the sheet and the ports along y = spec['y']."""
    y = spec["y"]
    x0, x1 = spec["x"]
    mid = (x0 + x1) / 2
    length = x1 - x0
    line_glow = glow("layer_line", accent, spec["line_strength"])
    line = box("layer.line", (length, spec["line_width"], 0.0006), (mid, y, 0.0003), line_glow.material)
    no_shadow(line)
    sheet_glow = glow("layer_sheet", accent, spec["sheet_strength"], alpha_ramp=True)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90.0), 3, "X"))
    bmesh.ops.scale(bm, vec=(length, 1.0, spec["sheet_height"]), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, spec["sheet_height"] / 2), verts=bm.verts)
    sheet = _mesh_object("layer.sheet", bm, sheet_glow.material)
    sheet.location = (mid, y, 0.0)
    no_shadow(sheet)
    sheet.visible_diffuse = False
    sheet.visible_glossy = False
    layer = Layer(line=line, line_glow=line_glow, sheet=sheet, sheet_glow=sheet_glow, y=y, x0=x0, x1=x1)
    return layer


def add_port(layer: Layer, name: str, x: float, metal: bpy.types.Material, accent: str) -> None:
    """A small machined port where a cable meets the layer, with a ring that lights."""
    ring = glow(f"port.{name}", accent, 3.0)
    base = cylinder(f"port.{name}", 0.0055, 0.004, (x, layer.y, 0.002), metal, bevel=0.0008)
    top = cylinder(f"port.{name}.ring", 0.0034, 0.0006, (0.0, 0.0, 0.0022), ring.material, parent=base)
    no_shadow(top)
    base.location = (x, layer.y, 0.002)
    layer.ports[name] = (base, ring)


@dataclass
class Bubble:
    """One bar of the chat panel."""

    obj: bpy.types.Object
    kind: str
    width: float
    height: float


@dataclass
class AgentDisplay:
    """The agent's display, a slim screen on a stand with an abstract chat panel."""

    root: bpy.types.Object
    screen_glow: Glow
    bubbles: list[Bubble]
    screen_size: tuple[float, float]
    base_point: Vector
    send: Glow


def build_agent(spec: dict[str, Any], mats: dict[str, bpy.types.Material], accent: str) -> AgentDisplay:
    """A 30 cm display on a foot, its screen facing the root's +x axis."""
    x, y = spec["position"]
    root = _empty("agent", (x, y, 0.0), spec["yaw_deg"])
    sw, sh = spec["screen"]
    pw, ph, pd = sw + 0.012, sh + 0.012, 0.007
    tilt = math.radians(spec.get("tilt_deg", 8.0))
    lift = spec.get("lift", 0.085)
    panel = _empty("agent.panel", (0.0, 0.0, lift + ph / 2), 0.0)
    panel.parent = root
    panel.rotation_euler = (0.0, -tilt, 0.0)
    box("agent.body", (pd, pw, ph), (-pd / 2, 0.0, 0.0), mats["aluminum"], 0.0028, panel)
    rounded_rect(
        "agent.glass",
        pw - 0.002,
        ph - 0.002,
        0.0032,
        mats["glass"],
        parent=panel,
        location=(0.0004, 0.0, 0.0),
        rotation=SCREEN,
    )
    screen_glow = glow("agent.screen", "#151614", 1.0)
    screen = rounded_rect(
        "agent.screen",
        sw,
        sh,
        0.002,
        screen_glow.material,
        parent=panel,
        location=(0.0008, 0.0, 0.0),
        rotation=SCREEN,
    )
    no_shadow(screen)
    box("agent.neck", (0.012, 0.05, lift + 0.05), (-0.022, 0.0, (lift + 0.05) / 2), mats["aluminum"], 0.003, root)
    box("agent.foot", (0.13, 0.11, 0.006), (-0.04, 0.0, 0.003), mats["aluminum"], 0.0025, root)
    bubbles: list[Bubble] = []
    colors = {"user": ("#43463f", 1.0), "agent": ("#cfd3cd", 0.32), "call": ("#eceeec", 0.5)}
    for i, kind in enumerate(spec["bubbles"]):
        color, strength = colors[kind["kind"]]
        g = glow(f"agent.bubble.{i}", color, strength)
        w = kind["width"] * sw
        bar = rounded_rect(
            f"agent.bubble.{i}",
            w,
            kind["height"],
            kind["height"] / 2,
            g.material,
            parent=panel,
            location=(0.0012, 0.0, 0.0),
            rotation=SCREEN,
            origin="left",
        )
        no_shadow(bar)
        if kind["kind"] == "call":
            tick = glow(f"agent.tick.{i}", accent, 4.0)
            mark = rounded_rect(
                f"agent.tick.{i}",
                0.003,
                kind["height"],
                0.0015,
                tick.material,
                parent=bar,
                location=(-0.0055, 0.0, 0.0002),
            )
            no_shadow(mark)
        bubbles.append(Bubble(obj=bar, kind=kind["kind"], width=w, height=kind["height"]))
    composer = glow("agent.composer", "#2a2c29", 1.0)
    comp = rounded_rect(
        "agent.composer",
        sw - 0.024,
        0.016,
        0.008,
        composer.material,
        parent=panel,
        location=(0.0011, 0.0, -sh / 2 + 0.016),
        rotation=SCREEN,
    )
    no_shadow(comp)
    send = glow("agent.send", accent, 2.5)
    dot = cylinder(
        "agent.send",
        0.0042,
        0.0004,
        (0.0014, sw / 2 - 0.02, -sh / 2 + 0.016),
        send.material,
        rotation=(0.0, math.radians(90.0), 0.0),
        parent=panel,
    )
    no_shadow(dot)
    back = Vector((x, y, 0.0)) + Matrix.Rotation(math.radians(spec["yaw_deg"]), 3, "Z") @ Vector((0.03, 0.0, 0.0))
    return AgentDisplay(
        root=root, screen_glow=screen_glow, bubbles=bubbles, screen_size=(sw, sh), base_point=back, send=send
    )


def key_bubbles(agent: AgentDisplay, stack: list[int], slide: float, frame: int) -> None:
    """Key the chat panel showing the bubbles in stack, newest last, sliding in by slide from 0 to 1."""
    sw, sh = agent.screen_size
    bottom = -sh / 2 + 0.034
    top = sh / 2 - 0.012
    gap = 0.0055
    shown = set()
    newest = stack[-1] if stack else None
    v = bottom - (1.0 - slide) * ((agent.bubbles[newest].height + gap) if newest is not None else 0.0)
    for index in reversed(stack):
        bubble = agent.bubbles[index]
        h = bubble.height
        center = v + h / 2
        if center + h / 2 > top:
            break
        if center - h / 2 >= bottom - 0.001:
            u = (sw / 2 - 0.014 - bubble.width) if bubble.kind == "user" else (-sw / 2 + 0.016)
            bubble.obj.location = (0.0012, u, center)
            grow = min(max(slide * 1.4, 0.0), 1.0) if index == newest else 1.0
            bubble.obj.scale = (max(grow, 1e-3), 1.0, 1.0)
            shown.add(index)
        v += h + gap
    for i, bubble in enumerate(agent.bubbles):
        if i not in shown:
            bubble.obj.scale = (1e-3, 1e-3, 1e-3)
        bubble.obj.keyframe_insert("location", frame=frame)
        bubble.obj.keyframe_insert("scale", frame=frame)
