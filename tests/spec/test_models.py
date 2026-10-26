"""Device file models. Shorthands, limits, confirmations and cross-checks."""

from __future__ import annotations

from typing import Any

import pytest

from openhal.spec import DeviceFileError, loads
from openhal.spec.loader import from_data, warnings_for

FAN = """
device: Desk fan controller
connect: { serial: auto, board: arduino-uno }
read:
  temperature: { unit: degC, every: 1s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
"""


def base(**extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "device": "Thing",
        "connect": {"driver": "mock"},
        "write": {"level": {"unit": "percent", "min": 0, "max": 100}},
        "safe_state": {"level": 0},
        "confirmed": {"by": "tester", "at": "2026-10-24"},
    }
    data.update(extra)
    return data


def problems(data: dict[str, Any]) -> str:
    with pytest.raises(DeviceFileError) as caught:
        from_data(data)
    return " | ".join(caught.value.problems)


def test_research_fan_is_valid_and_read_only() -> None:
    fan = loads(FAN)
    assert fan.device.name == "Desk fan controller"
    assert fan.device_id == "desk-fan-controller"
    assert fan.connect.driver == "serial"
    assert fan.connect.params == {"port": "auto", "board": "arduino-uno"}
    assert fan.write["fan_speed"].max_change_per_s == 20
    assert fan.effective_hazard == "medium"
    assert not fan.writable
    assert fan.unconfirmed() == ["file (interlocks, watchdog, safe state and hazard)", "write.fan_speed"]


def test_confirmation_makes_it_writable() -> None:
    fan = loads(FAN + "confirmed: { by: owner, at: 2026-10-24 }\n")
    assert fan.writable


def test_suggested_overrides_file_confirmation() -> None:
    data = base()
    data["write"]["level"]["suggested"] = True
    device = from_data(data)
    assert not device.writable


def test_per_channel_confirmation() -> None:
    data = base()
    del data["confirmed"]
    del data["safe_state"]
    data["write"]["level"]["confirmed"] = {"by": "tester", "at": "2026-10-24"}
    assert from_data(data).writable


def test_file_level_limits_need_a_file_confirmation() -> None:
    """Review finding F15. Per-channel confirmations don't cover interlocks, safe state or hazard."""
    data = base()
    del data["confirmed"]
    data["write"]["level"]["confirmed"] = {"by": "tester", "at": "2026-10-24"}
    device = from_data(data)
    assert not device.writable
    assert device.unconfirmed() == ["file (interlocks, watchdog, safe state and hazard)"]


def test_confirmation_bound_to_content() -> None:
    data = base()
    device = from_data(data)
    data["confirmed"] = {"by": "tester", "at": "2026-10-24", "sha256": device.limits_sha256()}
    bound = from_data(data)
    assert bound.writable
    data["write"]["level"]["max"] = 150
    changed = from_data(data)
    assert not changed.writable
    assert changed.unconfirmed() == ["file (limits changed after they were confirmed)"]
    data["write"]["level"]["max"] = 100
    data["notes"] = "Notes can change freely."
    assert from_data(data).writable


def test_limits_written_as_quantities_are_converted() -> None:
    data = base(write={"temp": {"unit": "degC", "min": "32 degF", "max": "100 degC", "max_change_per_s": "9 degF/s"}})
    data["safe_state"] = {"temp": "20 degC"}
    spec = from_data(data).write["temp"]
    assert spec.min == pytest.approx(0)
    assert spec.max == pytest.approx(100)
    assert spec.max_change_per_s == pytest.approx(5)


@pytest.mark.parametrize(
    ("write", "fragment"),
    [
        ({"x": {"min": 0, "max": 1}}, "need a unit"),
        ({"x": {"unit": "V"}}, "need both min and max"),
        ({"x": {"unit": "V", "min": 5, "max": 1}}, "is above max"),
        ({"x": {"unit": "V", "min": 0, "max": 1, "step": 0}}, "step must be greater"),
        ({"x": {"unit": "V", "min": 0, "max": 1, "max_change_per_s": -1}}, "greater than zero"),
        ({"x": {"type": "enum"}}, "non-empty values"),
        ({"x": {"type": "enum", "values": ["a", "a"]}}, "unique"),
        ({"x": {"type": "string"}}, "max_length"),
        ({"x": {"type": "bool", "min": 0}}, "only apply to number"),
        ({"x": {"unit": "blorbs", "min": 0, "max": 1}}, "Unknown unit"),
        ({"X": {"unit": "V", "min": 0, "max": 1}}, "pattern"),
    ],
)
def test_bad_write_channels(write: dict[str, Any], fragment: str) -> None:
    data = base(write=write)
    data.pop("safe_state")
    assert fragment in problems(data)


def test_unknown_keys_rejected_but_x_keys_kept() -> None:
    assert "Extra inputs" in problems(base(colour="red"))
    device = from_data(base(**{"x-vendor": {"anything": 1}}))
    assert device.extensions == {"x-vendor": {"anything": 1}}


def test_unknown_driver() -> None:
    assert "Unknown driver" in problems(base(connect={"driver": "teleport"}))
    assert "must name a driver" in problems(base(connect={"port": "auto"}))


def test_secrets_rejected() -> None:
    assert "must not hold secrets" in problems(base(connect={"driver": "http", "password": "hunter2"}))
    assert "must not hold secrets" in problems(base(connect={"driver": "http", "token": "abc"}))
    from_data(base(connect={"driver": "http", "token_env": "MY_TOKEN"}))


def test_duplicate_names_across_sections() -> None:
    data = base(read={"level": {"unit": "percent"}})
    assert "unique" in problems(data)


def test_safe_state_values_checked() -> None:
    assert "outside" in problems(base(safe_state={"level": 150}))
    assert "not a write channel" in problems(base(safe_state={"nope": 1}))
    assert "not an action" in problems(base(safe_state={"action": "park"}))


def test_interlocks_checked() -> None:
    good = base(interlocks=[{"if": "level > 10 %", "require": "other-device.flag == true"}])
    from_data(good)
    assert "not a channel" in problems(base(interlocks=[{"if": "nope > 1 %", "require": "level < 5 %"}]))
    assert "needs a unit" in problems(base(interlocks=[{"if": "level > 10", "require": "level < 50 %"}]))
    assert "ends too early" in problems(base(interlocks=[{"if": "level >", "require": "level < 50 %"}]))


def test_watchdog_rules() -> None:
    device = from_data(base(watchdog={"heartbeat": "2 s", "max_duration": [{"when": "level > 80 %", "for": "10 min"}]}))
    assert device.watchdog.max_duration[0].for_ == 600
    assert "heartbeat" in problems(base(watchdog={"heartbeat": "2 h"}))


def test_hazard_defaults() -> None:
    assert from_data(base()).effective_hazard == "medium"
    read_only = from_data({"device": "Sensor", "connect": {"driver": "mock"}, "read": {"t": {"unit": "degC"}}})
    assert read_only.effective_hazard == "low"
    assert read_only.writable


def test_verified_needs_report() -> None:
    assert "needs a report" in problems(base(provenance={"verification": {"status": "verified-on-hardware"}}))


def test_major_version_checked() -> None:
    assert "supports spec" in problems(base(openhal="2.0"))


def test_warnings() -> None:
    data = base()
    data.pop("safe_state")
    found = warnings_for(from_data(data))
    assert any("no safe_state" in warning for warning in found)
    assert any("treated as medium" in warning for warning in found)


def test_derived_ids() -> None:
    assert from_data(base(device="  3D Printer #2 ")).device_id == "device-3d-printer-2"
    assert from_data(base(id="psu")).device_id == "psu"
