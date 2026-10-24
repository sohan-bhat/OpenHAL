"""Parse a HID report descriptor into fields, and propose device file channels from them.

Written from the USB Device Class Definition for HID 1.11, section 6.2.2 (report descriptor
items) and the HID Usage Tables 1.5. Only short items are read. Long items are skipped, as the
spec allows. Push and Pop are honoured. Delimiters and string indexes are ignored.

A field is one data value in one report. Constant fields (padding) are dropped. Fields that start
on a byte boundary and are 8, 16 or 32 bits wide become number channels, and 1-bit fields become
bool channels with a byte offset and a mask. Anything else is listed in the notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Literal

Section = Literal["input", "output", "feature"]

_MAIN: Final[dict[int, Section]] = {0x8: "input", 0x9: "output", 0xB: "feature"}
_DESKTOP: Final = {
    0x30: "x",
    0x31: "y",
    0x32: "z",
    0x33: "rx",
    0x34: "ry",
    0x35: "rz",
    0x36: "slider",
    0x37: "dial",
    0x38: "wheel",
    0x39: "hat",
}
_LEDS: Final = {0x01: "num_lock", 0x02: "caps_lock", 0x03: "scroll_lock", 0x04: "compose", 0x05: "kana"}


@dataclass(frozen=True)
class Field:
    """One value in one report. `bit` counts from the start of the report payload, after any report id."""

    section: Section
    report: int
    bit: int
    size: int
    usage_page: int
    usage: int
    logical_min: int
    logical_max: int

    @property
    def name(self) -> str:
        if self.usage_page == 0x09:
            return f"button_{self.usage}"
        if self.usage_page == 0x08:
            return _LEDS.get(self.usage, f"led_{self.usage}")
        if self.usage_page == 0x01 and self.usage in _DESKTOP:
            return _DESKTOP[self.usage]
        return f"field_r{self.report}_b{self.bit}"


@dataclass
class _Globals:
    usage_page: int = 0
    logical_min: int = 0
    logical_max: int = 0
    report_size: int = 0
    report_count: int = 0
    report_id: int = 0


@dataclass
class Descriptor:
    fields: list[Field] = field(default_factory=list)
    uses_report_ids: bool = False
    skipped: list[str] = field(default_factory=list)


def _value(data: bytes, signed: bool) -> int:
    return int.from_bytes(data, "little", signed=signed) if data else 0


def parse(descriptor: bytes) -> Descriptor:
    """Walk the items. Raises ValueError for a truncated descriptor."""
    result = Descriptor()
    state = _Globals()
    stack: list[_Globals] = []
    usages: list[tuple[int, int]] = []
    usage_min: int | None = None
    offsets: dict[tuple[str, int], int] = {}
    index = 0
    while index < len(descriptor):
        prefix = descriptor[index]
        if prefix == 0xFE:
            if index + 1 >= len(descriptor):
                raise ValueError("truncated long item")
            index += 3 + descriptor[index + 1]
            continue
        size = (0, 1, 2, 4)[prefix & 0x03]
        kind = (prefix >> 2) & 0x03
        tag = prefix >> 4
        data = descriptor[index + 1 : index + 1 + size]
        if len(data) < size:
            raise ValueError(f"truncated item at byte {index}")
        index += 1 + size
        if kind == 1:
            if tag == 0x0:
                state.usage_page = _value(data, False)
            elif tag == 0x1:
                state.logical_min = _value(data, True)
            elif tag == 0x2:
                state.logical_max = _value(data, state.logical_min < 0)
            elif tag == 0x7:
                state.report_size = _value(data, False)
            elif tag == 0x8:
                state.report_id = _value(data, False)
                result.uses_report_ids = True
            elif tag == 0x9:
                state.report_count = _value(data, False)
            elif tag == 0xA:
                stack.append(_Globals(**vars(state)))
            elif tag == 0xB and stack:
                state = stack.pop()
        elif kind == 2:
            value = _value(data, False)
            page = (value >> 16) if size == 4 else state.usage_page
            if tag == 0x0:
                usages.append((page, value & 0xFFFF))
            elif tag == 0x1:
                usage_min = value & 0xFFFF
            elif tag == 0x2 and usage_min is not None:
                usages.extend((page, usage) for usage in range(usage_min, (value & 0xFFFF) + 1))
                usage_min = None
        elif kind == 0:
            section = _MAIN.get(tag)
            if section is not None:
                key = (section, state.report_id)
                start = offsets.get(key, 0)
                constant = bool(_value(data, False) & 0x01)
                for item in range(state.report_count):
                    bit = start + item * state.report_size
                    if constant or not usages:
                        continue
                    page, usage = usages[min(item, len(usages) - 1)]
                    result.fields.append(
                        Field(
                            section,
                            state.report_id,
                            bit,
                            state.report_size,
                            page,
                            usage,
                            state.logical_min,
                            state.logical_max,
                        )
                    )
                offsets[key] = start + state.report_count * state.report_size
            usages, usage_min = [], None
    return result


def propose(descriptor: Descriptor, limit: int = 64) -> dict[str, Any]:
    """Device file sections for the fields that map cleanly onto bytes and bits."""
    reads: dict[str, Any] = {}
    writes: dict[str, Any] = {}
    taken: set[str] = set()
    for item in descriptor.fields:
        if len(reads) + len(writes) >= limit:
            break
        if item.section == "feature":
            descriptor.skipped.append(f"feature report {item.report} bit {item.bit}")
            continue
        hid_map: dict[str, Any] = {"report": item.report, "byte": item.bit // 8}
        if item.section == "output":
            hid_map["kind"] = "output"
        if item.size == 1:
            hid_map["mask"] = 1 << (item.bit % 8)
            channel: dict[str, Any] = {"type": "bool", "map": hid_map}
        elif item.size in (8, 16, 32) and item.bit % 8 == 0:
            signed = item.logical_min < 0
            hid_map["format"] = f"{'int' if signed else 'uint'}{item.size}"
            channel = {"unit": "dimensionless", "map": hid_map}
            if item.logical_min < item.logical_max:
                if item.section == "input":
                    channel["range"] = [item.logical_min, item.logical_max]
                else:
                    channel["min"], channel["max"] = item.logical_min, item.logical_max
        else:
            descriptor.skipped.append(f"{item.section} report {item.report} bit {item.bit} ({item.size} bits)")
            continue
        if item.section == "output":
            if channel.get("type") != "bool" and "max" not in channel:
                descriptor.skipped.append(f"output report {item.report} bit {item.bit} (no logical range)")
                continue
            channel["suggested"] = True
        name, number = item.name, 2
        while name in taken:
            name = f"{item.name}_{number}"
            number += 1
        taken.add(name)
        (writes if item.section == "output" else reads)[name] = channel
    result: dict[str, Any] = {}
    if reads:
        result["read"] = reads
    if writes:
        result["write"] = writes
    notes = "Proposed from the HID report descriptor. Rename the channels after what they are on the device."
    if descriptor.skipped:
        notes += f" Not mapped: {'; '.join(descriptor.skipped[:20])}."
    result["notes"] = notes
    return result
