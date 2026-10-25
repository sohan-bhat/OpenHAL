"""The Python client of the OpenHAL hub's local API.

    from openhal.client import connect

    with connect() as hub:
        print(hub.read("plant-waterer", "soil_moisture").value)
        decision = hub.action("plant-waterer", "water", duration={"value": 20, "unit": "s"})
        print(decision.status, decision.message)

The client makes no safety decisions. The hub's kernel decides every command, and a blocked
command comes back as a `Decision`, not an exception. See docs/interfaces/PYTHON.md.
"""

from __future__ import annotations

from openhal.client.aio import AsyncClient, aconnect
from openhal.client.calls import split_target
from openhal.client.errors import (
    BadRequest,
    HubError,
    HubNotRunning,
    NotFound,
    NotSupported,
    OpenHALError,
    Refused,
    Unauthorized,
)
from openhal.client.models import (
    AuditEntry,
    ConfirmationRequest,
    Decision,
    DeviceSummary,
    DeviceView,
    HubStatus,
    Reading,
    Routine,
    RoutineSummary,
    StopReport,
    WriterSession,
)
from openhal.client.sync import Client, connect
from openhal.kernel.commands import Action, Write

__all__ = [
    "Action",
    "AsyncClient",
    "AuditEntry",
    "BadRequest",
    "Client",
    "ConfirmationRequest",
    "Decision",
    "DeviceSummary",
    "DeviceView",
    "HubError",
    "HubNotRunning",
    "HubStatus",
    "NotFound",
    "NotSupported",
    "OpenHALError",
    "Reading",
    "Refused",
    "Routine",
    "RoutineSummary",
    "StopReport",
    "Unauthorized",
    "Write",
    "WriterSession",
    "aconnect",
    "connect",
    "split_target",
]
