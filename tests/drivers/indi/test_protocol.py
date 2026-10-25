"""INDI XML parsing and message building, without a server."""

from __future__ import annotations

from xml.etree.ElementTree import fromstring

import pytest

from openhal.drivers.indi import protocol
from openhal.drivers.indi.protocol import ProtocolError


@pytest.mark.parametrize(
    ("text", "value"),
    [("12.5", 12.5), ("12:30:00", 12.5), ("-05 30 00", -5.5), ("+10:15", 10.25), (" 7 ", 7.0), ("1e3", 1000.0)],
)
def test_numbers_in_decimal_and_sexagesimal(text: str, value: float) -> None:
    assert protocol.parse_number(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["", "abc", "12:xx", "inf", "nan", "1:2:3:4"])
def test_bad_numbers_raise(text: str) -> None:
    with pytest.raises(ProtocolError):
        protocol.parse_number(text)


def test_stream_splits_top_level_elements_across_chunks() -> None:
    stream = protocol.Stream()
    first = stream.feed(b'<defTextVector device="A" name="B" state="Idle" perm="ro"><defText name="X">hel')
    assert first == []
    done = stream.feed(b'lo</defText></defTextVector>\n<message device="A" message="hi"/><setNum')
    assert [item.tag for item in done] == ["defTextVector", "message"]
    assert done[0][0].text == "hello"
    assert stream.feed(b'berVector device="A" name="N"/>')[0].tag == "setNumberVector"


@pytest.mark.parametrize(
    "chunks",
    [
        [b'<!DOCTYPE x [<!ENTITY a "b">]>'],
        [b"<defTextVector/>\n<", b"!DOCTYPE lol>"],
        [b'<!ENTITY lol "lol">'],
    ],
)
def test_document_type_and_entities_are_refused(chunks: list[bytes]) -> None:
    stream = protocol.Stream()
    for chunk in chunks[:-1]:
        stream.feed(chunk)
    with pytest.raises(ProtocolError, match="document type or entity"):
        stream.feed(chunks[-1])


def test_malformed_and_oversized_xml_raise() -> None:
    with pytest.raises(ProtocolError, match="malformed"):
        protocol.Stream().feed(b"<defTextVector></wrong>")
    small = protocol.Stream(limit=64)
    with pytest.raises(ProtocolError, match="longer than 64"):
        small.feed(b"<defTextVector>" + b"x" * 100)


def test_number_vector_definition_with_limits() -> None:
    element = fromstring(
        '<defNumberVector device="Mount" name="EQUATORIAL_EOD_COORD" state="Busy" perm="rw" group="Main">'
        '<defNumber name="RA" min="0" max="24" step="0" format="%010.6m">5:30:00</defNumber>'
        '<defNumber name="DEC" min="-90" max="90">22</defNumber></defNumberVector>'
    )
    vector = protocol.vector_from(element)
    assert (vector.kind, vector.state, vector.perm, vector.group) == ("number", "busy", "rw", "Main")
    assert vector.members["RA"].value == pytest.approx(5.5)
    assert (vector.members["DEC"].minimum, vector.members["DEC"].maximum) == (-90.0, 90.0)


def test_switch_light_and_text_definitions() -> None:
    switch = protocol.vector_from(
        fromstring(
            '<defSwitchVector device="D" name="S" rule="OneOfMany" state="Ok">'
            '<defSwitch name="A">On</defSwitch><defSwitch name="B">Off</defSwitch></defSwitchVector>'
        )
    )
    assert (switch.rule, switch.members["A"].value, switch.members["B"].value) == ("OneOfMany", True, False)
    light = protocol.vector_from(
        fromstring('<defLightVector device="D" name="L"><defLight name="X">Alert</defLight></defLightVector>')
    )
    assert (light.kind, light.perm, light.members["X"].value) == ("light", "ro", "alert")
    text = protocol.vector_from(
        fromstring('<defTextVector device="D" name="T"><defText name="X"> v1 </defText></defTextVector>')
    )
    assert text.members["X"].value == "v1"


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        ('<defNumberVector name="N"><defNumber name="A">1</defNumber></defNumberVector>', "no device"),
        ('<defNumberVector device="D" name="N" state="Weird"/>', "unknown property state"),
        ('<defSwitchVector device="D" name="S"><defSwitch name="A">Maybe</defSwitch></defSwitchVector>', "On or Off"),
        ('<defNumberVector device="D" name="N"><defNumber>1</defNumber></defNumberVector>', "has no name"),
        ('<setNumberVector device="D" name="N"/>', "not a property definition"),
    ],
)
def test_bad_definitions_raise(xml: str, message: str) -> None:
    with pytest.raises(ProtocolError, match=message):
        protocol.vector_from(fromstring(xml))


def test_updates_change_only_listed_members_and_are_all_or_nothing() -> None:
    vector = protocol.vector_from(
        fromstring(
            '<defNumberVector device="D" name="N"><defNumber name="A">1</defNumber>'
            '<defNumber name="B">2</defNumber></defNumberVector>'
        )
    )
    protocol.apply_update(
        vector,
        fromstring(
            '<setNumberVector device="D" name="N" state="Busy"><oneNumber name="A">5</oneNumber></setNumberVector>'
        ),
    )
    assert (vector.state, vector.members["A"].value, vector.members["B"].value) == ("busy", 5.0, 2.0)
    with pytest.raises(ProtocolError):
        protocol.apply_update(
            vector,
            fromstring(
                '<setNumberVector device="D" name="N" state="Ok"><oneNumber name="A">7</oneNumber>'
                '<oneNumber name="B">x</oneNumber></setNumberVector>'
            ),
        )
    assert (vector.state, vector.members["A"].value) == ("busy", 5.0)
    with pytest.raises(ProtocolError, match="doesn't match"):
        protocol.apply_update(vector, fromstring('<setSwitchVector device="D" name="N"/>'))


def test_outgoing_messages_escape_names() -> None:
    query = protocol.get_properties('Mount "A" & B', "EQUATORIAL_EOD_COORD")
    parsed = fromstring(query)
    assert (parsed.get("version"), parsed.get("device"), parsed.get("name")) == (
        "1.7",
        'Mount "A" & B',
        "EQUATORIAL_EOD_COORD",
    )
    switch = fromstring(protocol.new_vector("switch", "D", "S", {"A": True, "B": False}))
    assert [(child.tag, child.get("name"), child.text) for child in switch] == [
        ("oneSwitch", "A", "On"),
        ("oneSwitch", "B", "Off"),
    ]
    number = fromstring(protocol.new_vector("number", "D", "N", {"RA": 6.0}))
    assert (number.tag, number[0].text) == ("newNumberVector", "6")
    text = fromstring(protocol.new_vector("text", "D", "T", {"X": "<hi>"}))
    assert text[0].text == "<hi>"
