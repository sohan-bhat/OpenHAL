"""Property tests. For random limits and random command sequences, no executed write ever
violates a limit, a rate limit or an interlock (docs/SAFETY.md, Part 6.2)."""

from __future__ import annotations

import asyncio
import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel, Write, agent
from openhal.spec.loader import from_data
from tests.kernel.conftest import FakeClock

UNITS = [("percent", "%", 1.0), ("degC", "degC", 1.0), ("W", "W", 1.0)]
OTHER_UNITS = {"percent": ["dimensionless"], "degC": ["degF", "K"], "W": ["kW", "mW"]}


@st.composite
def channel(draw: st.DrawFn) -> dict[str, object]:
    unit, _, _ = draw(st.sampled_from(UNITS))
    low = draw(st.floats(-50, 50, allow_nan=False))
    high = low + draw(st.floats(0.5, 200, allow_nan=False))
    rate = draw(st.one_of(st.none(), st.floats(0.5, 100, allow_nan=False)))
    spec: dict[str, object] = {"unit": unit, "min": low, "max": high}
    if rate is not None:
        spec["max_change_per_s"] = rate
    return spec


@st.composite
def command(draw: st.DrawFn, unit: str) -> tuple[float, str, float]:
    """(seconds to wait first, value string, magnitude in the channel unit before conversion)."""
    wait = draw(st.floats(0, 5, allow_nan=False))
    shown = draw(st.sampled_from([unit, *OTHER_UNITS[unit]]))
    magnitude = draw(st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False))
    return wait, f"{magnitude} {shown}", magnitude


def device(spec: dict[str, object], interlock: bool) -> dict[str, object]:
    data: dict[str, object] = {
        "device": "Prop",
        "id": "prop",
        "connect": {"driver": "mock"},
        "write": {"level": spec, "gate": {"type": "bool"}},
        "hazard": "low",
        "confirmed": {"by": "prop", "at": "2026-10-24"},
    }
    if interlock:
        threshold = (float(spec["min"]) + float(spec["max"])) / 2  # type: ignore[arg-type]
        data["interlocks"] = [{"if": f"level > {threshold} {spec['unit']}", "require": "gate == true"}]
    return data


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    spec=channel(),
    interlock=st.booleans(),
    data=st.data(),
)
def test_no_executed_write_violates_limits(spec: dict[str, object], interlock: bool, data: st.DataObject) -> None:
    unit = str(spec["unit"])
    steps = data.draw(st.lists(command(unit), min_size=1, max_size=25))
    gates = data.draw(st.lists(st.booleans(), min_size=len(steps), max_size=len(steps)))

    async def scenario() -> None:
        clock = FakeClock()
        kernel = Kernel(clock=clock)
        file = from_data(device(spec, interlock))
        driver = MockDriver(file)
        kernel.register(file, driver)
        await kernel.connect("prop")
        clock.advance(1000)
        who = agent("prop", "control_low")
        history: list[tuple[float, float]] = []
        gate_state = False
        for (wait, value, _), gate in zip(steps, gates, strict=True):
            clock.advance(wait)
            gate_decision = await kernel.execute(Write(device="prop", channel="gate", value=gate), who)
            if gate_decision.status == "done":
                gate_state = gate
            decision = await kernel.execute(Write(device="prop", channel="level", value=value), who)
            if decision.status == "done":
                history.append((clock.now, float(decision.value)))
                accepted = float(decision.value)
                assert float(spec["min"]) - 1e-9 <= accepted <= float(spec["max"]) + 1e-9  # type: ignore[arg-type]
                if interlock:
                    threshold = (float(spec["min"]) + float(spec["max"])) / 2  # type: ignore[arg-type]
                    assert accepted <= threshold + 1e-9 or gate_state
            else:
                assert decision.status == "blocked"
        writes = [entry for entry in driver.hardware_writes() if entry[1] == "level"]
        assert [float(entry[2]) for entry in writes] == [value for _, value in history]
        rate = spec.get("max_change_per_s")
        if rate is not None:
            previous: tuple[float, float] | None = None
            for at, value in history:
                if previous is not None:
                    allowed = float(rate) * (at - previous[0])  # type: ignore[arg-type]
                    assert abs(value - previous[1]) <= allowed + 1e-6 or math.isclose(
                        abs(value - previous[1]), allowed, rel_tol=1e-6
                    )
                previous = (at, value)

    asyncio.run(scenario())


@settings(max_examples=100, deadline=None)
@given(
    value=st.one_of(
        st.integers(),
        st.floats(allow_nan=True, allow_infinity=True),
        st.text(max_size=30),
        st.booleans(),
        st.none(),
        st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
    )
)
def test_garbage_values_never_reach_the_driver(value: object) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        kernel = Kernel(clock=clock)
        file = from_data(device({"unit": "percent", "min": 0, "max": 100}, False))
        driver = MockDriver(file)
        kernel.register(file, driver)
        await kernel.connect("prop")
        clock.advance(1000)
        try:
            command = Write(device="prop", channel="level", value=value)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            return
        decision = await kernel.execute(command, agent("prop", "control_low"))
        if decision.status == "done":
            assert 0 <= float(decision.value) <= 100
        else:
            assert driver.hardware_writes() == []

    asyncio.run(scenario())
