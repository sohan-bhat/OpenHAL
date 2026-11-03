"""Find SO-101 joint angles that put the gripper at a point, for hand-keyed shots.

Damped least squares on the URDF's forward kinematics, in pure Python. The real
film takes its motion from a recording of the OpenHAL hub. This solver only
places keyframes for test shots and previews.
"""

from __future__ import annotations

import math

import so101_urdf as urdf

ARM = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")


def _tool(robot: urdf.Robot, values: dict[str, float]) -> urdf.Mat4:
    return urdf.link_poses(robot, values)[urdf.TOOL_LINK]


def _residual(
    tool: urdf.Mat4,
    target: tuple[float, float, float],
    approach: tuple[float, float, float],
    jaw: tuple[float, float, float] | None,
    weight: float,
) -> list[float]:
    res = [tool[i][3] - target[i] for i in range(3)]
    res += [weight * (tool[i][2] - approach[i]) for i in range(3)]
    if jaw is not None:
        res += [weight * (tool[i][0] - jaw[i]) for i in range(3)]
    return res


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [[*row[:], b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col and m[col][col] != 0.0:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col], strict=True)]
    return [m[i][n] / m[i][i] for i in range(n)]


def solve(
    robot: urdf.Robot,
    target: tuple[float, float, float],
    approach: tuple[float, float, float] = (0.0, 0.0, -1.0),
    jaw: tuple[float, float, float] | None = None,
    seed: dict[str, float] | None = None,
    iterations: int = 400,
) -> tuple[dict[str, float], float]:
    """Return joint values in radians and the remaining position error in meters.

    approach is the world direction the gripper points along (the tool z axis).
    jaw, if given, is the world direction of the tool x axis, which sets wrist_roll.
    """
    values = {name: 0.0 for name in ARM}
    if seed:
        values.update({k: v for k, v in seed.items() if k in ARM})
    weight = 0.08
    damping = 1e-4
    step = 1e-6
    for _ in range(iterations):
        res = _residual(_tool(robot, values), target, approach, jaw, weight)
        jac_cols = []
        for name in ARM:
            probe = dict(values)
            probe[name] += step
            moved = _residual(_tool(robot, probe), target, approach, jaw, weight)
            jac_cols.append([(m - r) / step for m, r in zip(moved, res, strict=True)])
        jtj = [[sum(ci[k] * cj[k] for k in range(len(res))) for cj in jac_cols] for ci in jac_cols]
        for i in range(len(ARM)):
            jtj[i][i] += damping
        jtr = [-sum(c[k] * res[k] for k in range(len(res))) for c in jac_cols]
        delta = _solve_linear(jtj, jtr)
        for name, d in zip(ARM, delta, strict=True):
            joint = robot.joint(name)
            values[name] = joint.clamp(values[name] + max(-0.2, min(0.2, d)))
        if max(abs(d) for d in delta) < 1e-9:
            break
    tool = _tool(robot, values)
    error = math.dist([tool[i][3] for i in range(3)], target)
    return values, error


def best(
    robot: urdf.Robot,
    target: tuple[float, float, float],
    approach: tuple[float, float, float] = (0.0, 0.0, -1.0),
    jaw: tuple[float, float, float] | None = None,
    seed: dict[str, float] | None = None,
) -> tuple[dict[str, float], float]:
    """Solve from many starting poses and keep the closest one, preferring the one nearest seed."""
    starts = [dict(seed)] if seed else []
    for lift in (-60.0, -20.0, 20.0):
        for elbow in (-40.0, 0.0, 40.0, 80.0):
            for flex in (-40.0, 20.0, 70.0):
                start = {
                    "shoulder_lift": math.radians(lift),
                    "elbow_flex": math.radians(elbow),
                    "wrist_flex": math.radians(flex),
                }
                if seed:
                    start["shoulder_pan"] = seed.get("shoulder_pan", 0.0)
                    start["wrist_roll"] = seed.get("wrist_roll", 0.0)
                starts.append(start)
    found = []
    for start in starts:
        values, _ = solve(robot, target, approach, jaw, start, iterations=120)
        cost = sum(r * r for r in _residual(_tool(robot, values), target, approach, jaw, 0.08))
        found.append((cost, values))
    floor = min(c for c, _ in found)
    near = [v for c, v in found if c <= floor * 4 + 1e-8]
    if seed:
        near.sort(key=lambda v: sum((v[k] - seed.get(k, 0.0)) ** 2 for k in ARM))
    return solve(robot, target, approach, jaw, near[0], iterations=400)
