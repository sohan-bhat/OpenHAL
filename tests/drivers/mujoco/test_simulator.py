"""The MuJoCo world behind the mujoco driver. Skipped when the mujoco extra isn't installed."""

from __future__ import annotations

import math
import time

import pytest

mujoco = pytest.importorskip("mujoco")

from openhal.drivers.mujoco.conformance import BENCH_ARM  # noqa: E402
from openhal.drivers.mujoco.simulator import Aim, World, halton, minimum_jerk  # noqa: E402

DOWN = Aim((1.0, 0.0, 0.0), (0.0, 0.0, -1.0))


def world(xml: str = BENCH_ARM, keyframe: str | None = "rest") -> World:
    return World(mujoco.MjModel.from_xml_string(xml), keyframe=keyframe)


def ids(model: object, kind: object, *names: str) -> list[int]:
    return [mujoco.mj_name2id(model, kind, name) for name in names]


def test_a_minimum_jerk_path_starts_and_ends_at_rest() -> None:
    assert minimum_jerk(-1.0) == 0.0
    assert minimum_jerk(0.5) == pytest.approx(0.5)
    assert minimum_jerk(2.0) == 1.0
    assert [halton(1, 2), halton(2, 2), halton(3, 3)] == [0.5, 0.25, pytest.approx(1 / 9)]


def test_a_world_starts_from_its_keyframe_and_reads_positions() -> None:
    sim = world()
    assert sim.timestep == pytest.approx(0.002)
    assert sim.qpos(1) == pytest.approx(-0.9)
    block = mujoco.mj_name2id(sim.model, mujoco.mjtObj.mjOBJ_BODY, "block")
    assert sim.body_position(block) == pytest.approx((0.3, 0.1, 0.02))
    tip = mujoco.mj_name2id(sim.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
    assert sim.site_position(tip)[0] == pytest.approx(0.138, abs=1e-3)
    sim.advance(10)
    assert sim.time == pytest.approx(0.02)
    assert sim.steps == 10
    with pytest.raises(KeyError):
        world(keyframe="nowhere")


def test_a_move_never_passes_its_speed_and_arrives() -> None:
    sim = world()
    speed = math.radians(90)
    motion = sim.move([({0: 0.5}, {0: speed})])
    assert sim.goal(0) == pytest.approx(0.5)
    previous, fastest = float(sim.data.ctrl[0]), 0.0
    while not motion.over:
        sim.advance()
        now = float(sim.data.ctrl[0])
        fastest = max(fastest, abs(now - previous) / sim.timestep)
        previous = now
    assert sim.data.ctrl[0] == pytest.approx(0.5)
    assert fastest <= speed * 1.001
    assert fastest > speed * 0.95
    assert motion.ended is None
    assert sim.motions == []


def test_a_goal_without_a_speed_is_set_at_once() -> None:
    sim = world()
    motion = sim.move([({4: 0.02}, {4: None})])
    sim.advance()
    assert motion.over
    assert sim.data.ctrl[4] == pytest.approx(0.02)


def test_phases_run_one_after_another() -> None:
    sim = world()
    motion = sim.move([({0: 0.2}, {0: 2.0}), ({4: 0.03}, {4: 0.1})])
    sim.advance()
    assert sim.data.ctrl[4] == pytest.approx(0.01)
    while motion.phases and 0 in motion.phases[0].goals:
        sim.advance()
    assert sim.data.ctrl[0] == pytest.approx(0.2)
    while not motion.over:
        sim.advance()
    assert sim.data.ctrl[4] == pytest.approx(0.03)
    assert sim.goal(4) == pytest.approx(0.03)


def test_a_newer_move_takes_over_only_the_actuators_it_names() -> None:
    sim = world()
    first = sim.move([({0: 0.5, 1: -0.5}, {0: 1.0, 1: 1.0})])
    sim.advance(5)
    second = sim.move([({1: -1.0}, {1: 1.0})])
    assert first.actuators() == {0}
    assert not first.over
    assert first.ended == "taken over"
    assert second.ended is None
    sim.move([({0: 0.0}, {0: 1.0})])
    assert first.over
    assert first not in sim.motions
    assert second in sim.motions


def test_hold_ends_every_move_and_keeps_the_setpoints() -> None:
    sim = world()
    motion = sim.move([({0: 1.0}, {0: 1.0})])
    sim.advance(100)
    where = float(sim.data.ctrl[0])
    sim.hold()
    assert motion.ended == "held"
    assert motion.over
    assert sim.motions == []
    assert sim.goal(0) == pytest.approx(where)
    sim.advance(200)
    assert sim.data.ctrl[0] == pytest.approx(where)
    assert sim.qpos(0) == pytest.approx(where, abs=1e-3)


def test_a_watcher_sees_every_nth_step_until_removed() -> None:
    sim = world()
    seen: list[float] = []
    remove = sim.watch(5, lambda moment, data: seen.append(moment))
    sim.advance(12)
    assert seen == [pytest.approx(0.01), pytest.approx(0.02)]
    remove()
    remove()
    sim.advance(10)
    assert len(seen) == 2


def test_the_thread_keeps_simulated_time_with_the_clock() -> None:
    sim = world()
    sim.start()
    sim.start()
    try:
        time.sleep(0.3)
        assert sim.running
        assert sim.time > 0.1
        assert sim.lag_s < 0.25
    finally:
        sim.close()
    assert not sim.running
    sim.close()


def test_a_failing_watcher_stops_the_thread_with_a_reason() -> None:
    sim = world()

    def broken(moment: float, data: object) -> None:
        raise RuntimeError("boom")

    sim.watch(1, broken)
    sim.start()
    deadline = time.monotonic() + 5
    while sim.failure is None and time.monotonic() < deadline:
        time.sleep(0.01)
    sim.close()
    assert sim.failure == "the physics thread stopped (RuntimeError: boom)"
    assert not sim.running


def test_an_unstable_simulation_is_reported() -> None:
    sim = world()
    sim.data.warning[mujoco.mjtWarning.mjWARN_BADQACC].number = 1
    sim.start()
    deadline = time.monotonic() + 5
    while sim.running and time.monotonic() < deadline:
        time.sleep(0.01)
    sim.close()
    assert sim.failure == "the simulation became unstable and MuJoCo reset it"
    assert sim.steps == 1


def _limits(sim: World) -> dict[int, tuple[float, float]]:
    return {joint: (float(sim.model.jnt_range[joint][0]), float(sim.model.jnt_range[joint][1])) for joint in range(4)}


def test_solve_puts_the_site_at_a_point_with_its_aim() -> None:
    sim = world()
    tip = mujoco.mj_name2id(sim.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
    solution = sim.solve(tip, (0.2, 0.05, 0.05), _limits(sim), aim=DOWN, speeds={0: 1.0})
    assert solution.reached
    assert solution.error_m < 1e-3
    assert solution.aim_error_rad < math.radians(1)
    sim.data.qpos[list(solution.joints)] = list(solution.joints.values())
    mujoco.mj_kinematics(sim.model, sim.data)
    assert sim.data.site_xpos[tip] == pytest.approx((0.2, 0.05, 0.05), abs=1e-3)


def test_solve_without_an_aim_and_without_keyframes() -> None:
    sim = world(BENCH_ARM.split("<keyframe>")[0] + "</mujoco>", keyframe=None)
    tip = mujoco.mj_name2id(sim.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
    solution = sim.solve(tip, (0.15, -0.05, 0.12), _limits(sim))
    assert solution.reached
    assert solution.aim_error_rad == 0.0


def test_solve_returns_the_closest_miss_out_of_reach() -> None:
    sim = world()
    tip = mujoco.mj_name2id(sim.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
    solution = sim.solve(tip, (0.6, 0.0, 0.0), _limits(sim), aim=DOWN)
    assert not solution.reached
    assert solution.error_m > 0.2
    narrow = {joint: (0.0, 0.0) for joint in range(4)}
    assert not sim.solve(tip, (0.2, 0.0, 0.05), narrow).reached
