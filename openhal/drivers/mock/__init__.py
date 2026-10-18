"""The mock driver. A simulated device for tests, demos and the conformance suite."""

from __future__ import annotations

NAME = "mock"
ENTRY = "openhal.drivers.mock.driver:MockDriver"

from openhal.drivers.mock.driver import MockDriver, MockParams  # noqa: E402 (after the registry constants)

__all__ = ["ENTRY", "NAME", "MockDriver", "MockParams"]
