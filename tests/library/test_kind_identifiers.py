"""A USB class or an mDNS service type names a kind of device, so it never makes a match alone."""

from __future__ import annotations

from openhal.drivers.base import Discovered
from openhal.hub.discovery import score
from openhal.spec import loads

PADS = loads(
    """
device: { name: Pads, model: LPD8, manufacturer: Akai }
match: { usb: ["09e8:0075"], usb_class: midi }
connect: { midi: LPD8 }
read:
  knob: { unit: percent, map: { cc: 1 } }
"""
)

NODE = loads(
    """
device: Node
match:
  mdns: _esphomelib._tcp
  esphome: { project_name: "Vendor.Node" }
connect: { esphome: node.local }
read:
  temperature: { unit: degC }
"""
)


def test_a_usb_class_alone_is_not_a_match() -> None:
    assert score(PADS, Discovered("midi", "Keyboard", {"usb_class": "midi"})) == 0


def test_a_usb_class_adds_to_a_product_match() -> None:
    product = score(PADS, Discovered("midi", "LPD8", {"usb": "09E8:0075"}))
    both = score(PADS, Discovered("midi", "LPD8", {"usb": "09e8:0075", "usb_class": "midi"}))
    assert product > 0
    assert both == product + 1


def test_an_mdns_type_alone_is_not_a_match() -> None:
    assert score(NODE, Discovered("esphome", "other.local", {"mdns": "_esphomelib._tcp"})) == 0
    found = Discovered("esphome", "node.local", {"mdns": "_esphomelib._tcp", "esphome.project_name": "Vendor.Node"})
    assert score(NODE, found) == 5


def test_another_driver_never_matches() -> None:
    assert score(PADS, Discovered("hid", "LPD8", {"usb": "09e8:0075"})) == 0
