"""Deck layouts and resource addresses for the PyLabRobot driver.

A deck comes from a JSON file saved by PyLabRobot (`deck.save("deck.json")`), or from a layout in
the device file that names PyLabRobot resource factories.

    layout:
      - { name: tips, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }
      - { name: plate, resource: cor_96_wellplate_360uL_Fb, rails: 9 }

Actions address tip spots and wells as `<resource>:<spot>` or `<resource>:<first>:<last>`, for
example `tips:A1` or `plate:A1:H1`, which is PyLabRobot's own range syntax after the colon.
"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openhal.drivers.base import DriverError

DECKS: Final = {
    "starlet": ("pylabrobot.resources.hamilton", "STARLetDeck"),
    "star": ("pylabrobot.resources.hamilton", "STARDeck"),
    "ot2": ("pylabrobot.resources.opentrons", "OTDeck"),
    "evo150": ("pylabrobot.resources.tecan", "EVO150Deck"),
}
ADDRESS: Final = re.compile(
    r"^([A-Za-z0-9_\-]{1,64}):([A-P](?:[1-9]|[1-3][0-9]|4[0-8]))(?::([A-P](?:[1-9]|[1-3][0-9]|4[0-8])))?$"
)


class Placement(BaseModel):
    """One resource on the deck."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,64}$")
    resource: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,120}$")
    rails: int | None = Field(default=None, ge=1, le=72)
    slot: int | None = Field(default=None, ge=1, le=12)

    @model_validator(mode="after")
    def _one(self) -> Placement:
        if (self.rails is None) == (self.slot is None):
            raise ValueError("give exactly one of rails (Hamilton, Tecan) or slot (Opentrons).")
        return self


def _resources() -> Any:
    import pylabrobot.resources as resources  # type: ignore[import-untyped]

    return resources


def build(kind: str, layout: list[Placement], deck_file: str | None) -> Any:
    """Make the deck and put every resource of the layout on it."""
    import importlib

    resources = _resources()
    if deck_file is not None:
        try:
            return resources.Deck.load_from_json_file(deck_file)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DriverError(f"Could not load the deck file {deck_file} ({exc}).") from exc
    module, name = DECKS[kind]
    deck = getattr(importlib.import_module(module), name)()
    for placement in layout:
        factory = getattr(resources, placement.resource, None)
        if not callable(factory) or isinstance(factory, type):
            raise DriverError(f"layout {placement.name}: {placement.resource} is not a PyLabRobot resource factory.")
        try:
            resource = factory(name=placement.name)
        except TypeError as exc:
            raise DriverError(f"layout {placement.name}: {placement.resource} can't be built ({exc}).") from exc
        try:
            if placement.slot is not None:
                if not hasattr(deck, "assign_child_at_slot"):
                    raise DriverError(f"layout {placement.name}: the {kind} deck has rails, not slots.")
                deck.assign_child_at_slot(resource, placement.slot)
            else:
                deck.assign_child_resource(resource, rails=placement.rails)
        except DriverError:
            raise
        except Exception as exc:
            raise DriverError(
                f"layout {placement.name}: PyLabRobot returned an error for the placement ({exc})."
            ) from exc
    return deck


def parse(address: str) -> tuple[str, str]:
    """Split `plate:A1:H1` into the resource name and PyLabRobot's identifier, `A1:H1`."""
    match = ADDRESS.match(address)
    if match is None:
        raise DriverError(f"{address!r} is not a deck address such as plate:A1 or tips:A1:H1.")
    first, last = match.group(2), match.group(3)
    return match.group(1), f"{first}:{last}" if last else first


def items(deck: Any, address: str, kind: str) -> list[Any]:
    """The tip spots or wells an address names. `kind` is TipRack or a container holder."""
    resources = _resources()
    name, identifier = parse(address)
    try:
        resource = deck.get_resource(name)
    except resources.ResourceNotFoundError:
        raise DriverError(f"The deck has no resource {name!r}. Check the layout.") from None
    wanted = resources.TipRack if kind == "tips" else resources.ItemizedResource
    if not isinstance(resource, wanted) or (kind != "tips" and isinstance(resource, resources.TipRack)):
        raise DriverError(f"{name} is a {type(resource).__name__}, not a {'tip rack' if kind == 'tips' else 'plate'}.")
    try:
        found = resource[identifier]
    except (IndexError, KeyError, ValueError) as exc:
        raise DriverError(f"{name} has no {identifier} ({exc}).") from exc
    return list(found)
