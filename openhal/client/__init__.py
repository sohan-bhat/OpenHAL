"""The Python client of the OpenHAL hub's local API.

    from openhal.client import connect

    with connect() as hub:
        print(hub.read("printer", "bed_temp").value)
        decision = hub.write("printer", "bed_target", 70, "degC")
        print(decision.status, decision.message)

The client makes no safety decisions. The hub's kernel checks every command, and a blocked
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
    FindResult,
    HubStatus,
    Image,
    Reading,
    Routine,
    RoutineSummary,
    RunCaps,
    SampleResult,
    StepRun,
    StopReport,
    WaitResult,
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
    "FindResult",
    "HubError",
    "HubNotRunning",
    "HubStatus",
    "Image",
    "NotFound",
    "NotSupported",
    "OpenHALError",
    "Reading",
    "Refused",
    "Routine",
    "RoutineSummary",
    "RunCaps",
    "SampleResult",
    "StepRun",
    "StopReport",
    "Unauthorized",
    "WaitResult",
    "Write",
    "WriterSession",
    "aconnect",
    "connect",
    "split_target",
]
