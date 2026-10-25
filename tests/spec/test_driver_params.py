"""No driver takes a file path from a device file (THREAT_MODEL T16).

A device file may come from the library, a vendor or an AI draft, so the hub never opens a file it
names. A driver that needs a certificate or a key takes the name of an environment variable that
holds the path, the way `token_env` holds a secret. Device paths such as a serial port are
addresses, not files the hub reads.
"""

from __future__ import annotations

import pytest

from openhal.drivers import registry

FILE_WORDS = ("_file", "_dir", "_path", "cert_path", "keyfile", "certfile")
URL_PATHS = {("onvif", "device_path")}
"""Parameters whose name ends like a file but hold a URL path on the device, never a local file."""


def _params(name: str) -> list[str]:
    try:
        model = registry.load(name).params_model
    except registry.UnknownDriver:
        pytest.skip(f"{name} needs an optional dependency that isn't installed")
    return list(getattr(model, "model_fields", {}))


@pytest.mark.parametrize("name", registry.names())
def test_no_driver_parameter_names_a_file(name: str) -> None:
    fields = _params(name)
    named = [field for field in fields if field.endswith(FILE_WORDS) and (name, field) not in URL_PATHS]
    assert not named, f"{name} takes {named} from the device file. Take an environment variable name instead."


@pytest.mark.parametrize("name", ["sila2", "bambu", "mqtt", "zigbee-zwave"])
def test_certificates_come_from_the_environment(name: str) -> None:
    fields = _params(name)
    assert "ca_env" in fields
    assert "ca_file" not in fields


def test_a_deck_layout_file_comes_from_the_environment() -> None:
    fields = _params("pylabrobot")
    assert "deck_env" in fields
    assert "deck_file" not in fields
