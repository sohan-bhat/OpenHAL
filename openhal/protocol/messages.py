"""Pydantic models for every protocol message (ADR 0015).

Field names are snake_case in Python and camelCase on the wire. Params models refuse unknown fields,
so a typo is INVALID_PARAMS instead of being ignored. `METHODS` and `NOTIFICATIONS` list every method
and notification with its models and conformance level. The schema reference in spec/2026-10-24/ is
generated from this module by `python -m openhal.protocol.schema`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Conformance = Literal["core", "control", "full"]
Hazard = Literal["low", "medium", "high"]
PrincipalKind = Literal["human", "agent", "routine", "system"]
Scope = Literal["read", "control_low", "control_medium"]
DecisionStatus = Literal["allowed", "blocked", "needs_confirmation", "done", "pending", "failed"]
RequestStatus = Literal["pending", "approved", "rejected", "expired", "cancelled", "blocked", "done", "failed"]
Value = str | bool | int | float
"""A command value. Numbers need a unit, so they travel as quantity strings such as `"60 %"`."""

DeviceId = Annotated[str, Field(min_length=1, max_length=48, description="A device id, for example desk-fan.")]
ChannelName = Annotated[str, Field(min_length=1, max_length=48, description="A channel, for example fan_speed.")]
ActionName = Annotated[str, Field(min_length=1, max_length=48, description="An action, for example home.")]
RequestId = Annotated[str, Field(min_length=1, max_length=64, description="A confirmation request id.")]

LEVELS: Final[dict[Conformance, int]] = {"core": 0, "control": 1, "full": 2}


class Message(BaseModel):
    """Base for every protocol model. camelCase on the wire, unknown fields refused."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    def wire(self) -> dict[str, Any]:
        """The model as it travels, with camelCase names."""
        return self.model_dump(mode="json", by_alias=True)


class Empty(Message):
    """Params for methods that take none."""


class ErrorData(Message):
    """`error.data`. `name` is the registry name clients branch on."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")

    name: str = Field(description="The registry name, for example LIMIT_EXCEEDED.")
    kernel_code: str | None = Field(default=None, description="The kernel's block code, for example above_max.")
    kernel_message: str | None = Field(default=None, description="The kernel's own message.")
    device: str | None = None
    channel: str | None = None
    action: str | None = None
    limit: dict[str, Any] | None = Field(default=None, description='The limit that applied, as {"max": "100 %"}.')
    requested: str | None = Field(default=None, description="The requested value in the channel unit.")
    file: str | None = Field(default=None, description="The device file name, for example desk-fan.hal.yaml.")
    confirmed_by: str | None = Field(default=None, description="Who confirmed the limit.")
    confirmed_at: str | None = Field(default=None, description="When the limit was confirmed.")
    request_id: str | None = None


class ErrorObject(Message):
    """The JSON-RPC `error` member."""

    code: int = Field(description="The registry number, stable across versions.")
    message: str = Field(description="The human-readable reason, formed from data.")
    data: ErrorData | None = None


class Request(Message):
    """A JSON-RPC request. It has an id and expects a response."""

    jsonrpc: Literal["2.0"]
    id: int | str
    method: str
    params: dict[str, Any] | None = None


class Notification(Message):
    """A JSON-RPC notification. It has no id and gets no response."""

    jsonrpc: Literal["2.0"]
    method: str
    params: dict[str, Any] | None = None


class Success(Message):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    result: dict[str, Any]


class Failure(Message):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None
    error: ErrorObject


class Info(Message):
    """`clientInfo` and `hubInfo`."""

    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)


class InitializeParams(Message):
    protocol_version: str = Field(max_length=10, description="The newest version the client supports.")
    client_info: Info
    token: str | None = Field(default=None, max_length=200, description="The bearer token, if not sent as a header.")


class PrincipalInfo(Message):
    kind: PrincipalKind
    name: str
    scope: Scope


class Capabilities(Message):
    notifications: list[str] = Field(description="Every notification this hub sends.")


class InitializeResult(Message):
    protocol_version: str
    hub_info: Info
    conformance: Conformance
    principal: PrincipalInfo
    capabilities: Capabilities


class DeviceSummary(Message):
    id: str
    name: str
    model: str | None = None
    manufacturer: str | None = None
    driver: str
    hazard: Hazard
    writable: bool = Field(description="False until a person confirms every limit.")
    connected: bool
    unavailable: str | None = Field(default=None, description="Why the device can't take commands, if it can't.")
    last_error: str | None = Field(default=None, description="The driver's last error, inside a device-data block.")
    verification: str
    source: str
    conformance: Conformance = Field(description="The driver's declared conformance level.")


class DevicesListResult(Message):
    devices: list[DeviceSummary]


class DescribeParams(Message):
    device: DeviceId


class Confirmed(Message):
    by: str
    at: str


class Current(Message):
    """The latest known value of a channel."""

    value: Any = None
    known: bool
    age_s: float | None = None


class ReadChannelInfo(Current):
    type: str
    unit: str | None = None
    every_s: float | None = None
    stream: bool = False
    range: list[float] | None = None
    values: list[str] | None = None


class WriteChannelInfo(Current):
    type: str
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    max_change_per_s: float | None = None
    values: list[str] | None = None
    max_length: int | None = None
    pattern: str | None = None
    confirm: str
    suggested: bool
    confirmed: Confirmed | None = Field(default=None, description="Who confirmed this channel's limits.")


class ActionInfo(Message):
    description: str | None = None
    args: dict[str, dict[str, Any]]
    require: list[str]
    effects: list[str]
    confirm: str
    suggested: bool
    confirmed: Confirmed | None = None


class InterlockInfo(Message):
    if_: str = Field(alias="if")
    require: str
    message: str | None = None


class MaxDurationInfo(Message):
    when: str
    for_s: float
    reset_after_s: float | None = None
    then: Any


class WatchdogInfo(Message):
    heartbeat_s: float
    on_loss: str | None = None
    max_duration: list[MaxDurationInfo]


class LimitsProvenance(Message):
    """Where the limits come from and who confirmed them."""

    file: str | None = Field(description="The device file name, for example desk-fan.hal.yaml.")
    confirmed: Confirmed | None = Field(description="The file-level confirmation.")
    bound: bool = Field(description="True when the confirmation is bound to a hash of the limits.")
    unconfirmed: list[str] = Field(description="Limits no person has confirmed yet.")
    source: str
    by: str | None = None
    at: str | None = None


class DeviceDescription(DeviceSummary):
    read: dict[str, ReadChannelInfo]
    write: dict[str, WriteChannelInfo]
    actions: dict[str, ActionInfo]
    interlocks: list[InterlockInfo]
    watchdog: WatchdogInfo
    safe_state: list[dict[str, Any]]
    safe_state_support: str
    notes: str | None = Field(default=None, description="Device file notes, inside a device-data block.")
    warnings: list[str]
    limits_provenance: LimitsProvenance


class DescribeResult(Message):
    device: DeviceDescription


class ReadParams(Message):
    device: DeviceId
    channel: ChannelName


class Reading(Message):
    device: str
    channel: str
    value: Any = Field(description="The value in `unit`. Text is inside a device-data block.")
    unit: str | None = None
    at: float = Field(description="Unix time of the reading.")
    suspect: bool = False


class ReadFailure(Message):
    device: str
    channel: str
    error: ErrorObject


class ReadManyParams(Message):
    items: list[ReadParams] = Field(max_length=100)


class ReadManyResult(Message):
    readings: list[Reading | ReadFailure]


class WriteParams(Message):
    device: DeviceId
    channel: ChannelName
    value: Value = Field(description='A quantity string like "60 %", a bool, or an enum value.')


class WriteDone(Message):
    status: Literal["done"] = "done"
    device: str
    channel: str
    value: Any
    unit: str | None = None


class Pending(Message):
    status: Literal["pending"] = "pending"
    request_id: str
    expires_in_s: float


class WriteCommand(Message):
    kind: Literal["write"] = "write"
    device: DeviceId
    channel: ChannelName
    value: Value


class ActionCommand(Message):
    kind: Literal["action"] = "action"
    device: DeviceId
    action: ActionName
    args: dict[str, Value] = {}


class WaitStep(Message):
    kind: Literal["wait"] = "wait"
    wait: str = Field(max_length=40, description='A duration with a unit, for example "2 s". At most 1 h.')


Command = Annotated[WriteCommand | ActionCommand, Field(discriminator="kind")]
Step = Annotated[WriteCommand | ActionCommand | WaitStep, Field(discriminator="kind")]


class Decision(Message):
    """The kernel's answer to one command. A blocked decision carries the registry error."""

    status: DecisionStatus
    device: str
    target: str = Field(description="write:<channel> or action:<action>.")
    value: Any = None
    unit: str | None = None
    request_id: str | None = None
    step: str | None = Field(default=None, description="Where the command sits in a plan or routine.")
    error: ErrorObject | None = None


class DryRunParams(Message):
    commands: list[Command] = Field(max_length=200)


class DryRunResult(Message):
    decisions: list[Decision]


class PlanCheckParams(Message):
    steps: list[Step] = Field(max_length=200)


class PlanResult(Message):
    ok: bool = Field(description="True when every step would run now without a person.")
    decisions: list[Decision]
    problems: list[str]


class StopParams(Message):
    reason: str | None = Field(default=None, max_length=200)


class StopDevice(Message):
    device: str
    status: str = Field(description="safe, partial, failed, pending or no_safe_state.")
    detail: str


class StopResult(Message):
    devices: list[StopDevice]


class ActionParams(Message):
    device: DeviceId
    action: ActionName
    args: dict[str, Value] = {}


class ActionOutcome(Message):
    device: str
    action: str
    args: dict[str, Any]


class ActionDone(Message):
    status: Literal["done"] = "done"
    result: ActionOutcome


class ConfirmationRequest(Message):
    request_id: str
    status: RequestStatus
    command: Command
    requested_by: str
    expires_in_s: float
    dry_run: Decision
    decided_by: str | None = None
    result: Decision | None = None


class ConfirmationsListParams(Message):
    status: RequestStatus | None = None


class ConfirmationsListResult(Message):
    requests: list[ConfirmationRequest]


class ApproveParams(Message):
    request_id: RequestId


class RejectParams(Message):
    request_id: RequestId
    reason: str | None = Field(default=None, max_length=200)


class UnlockParams(Message):
    phrase: str = Field(max_length=40, description="Type unlock.")


class UnlockResult(Message):
    ok: bool


class RoutineSummary(Message):
    id: str
    kind: str
    enabled: bool
    sha256: str
    devices: list[str]
    max_hazard: str | None = None
    triggers: list[Any]
    drafted_by: str | None = None
    enabled_by: str | None = None
    disabled_reason: str | None = None
    last_run: dict[str, Any] | None = None


class RoutinesListResult(Message):
    routines: list[RoutineSummary]


class RoutineDryRunParams(Message):
    routine_id: str = Field(min_length=1, max_length=48)


class AuditQueryParams(Message):
    device: str | None = Field(default=None, max_length=48)
    status: str | None = Field(default=None, max_length=40)
    event: str | None = Field(default=None, max_length=40)
    since: int = Field(default=0, ge=0, description="Only entries after this sequence number.")
    limit: int = Field(default=50, ge=1, le=500)


class AuditEntry(Message):
    seq: int
    at: float
    event: str
    principal: str
    device: str | None = None
    target: str | None = None
    status: str | None = None
    code: str | None = None
    details: dict[str, Any]
    hash: str


class AuditQueryResult(Message):
    entries: list[AuditEntry]


class BlockedParams(Message):
    device: str
    target: str
    error: ErrorObject


class StoppedDevice(Message):
    device: str
    status: str


class StoppedParams(Message):
    reason: str
    by: str
    devices: list[StoppedDevice]


class DeviceAddedParams(Message):
    device: DeviceSummary


class DeviceRemovedParams(Message):
    device: str


class ConfirmationRequestedParams(Message):
    request: ConfirmationRequest


class LogEntry(Message):
    """One message in the Inspector's log, from `GET /v1/rpc/log`."""

    seq: int
    at: float
    direction: Literal["in", "out"]
    client: str | None = None
    principal: str | None = None
    message: Any


@dataclass(frozen=True, slots=True)
class MethodSpec:
    """One method. `human_only` methods answer SCOPE_DENIED to every other principal."""

    params: type[Message]
    result: Any
    level: Conformance
    human_only: bool = False


METHODS: Final[dict[str, MethodSpec]] = {
    "hal/initialize": MethodSpec(params=InitializeParams, result=InitializeResult, level="core"),
    "hal/devices/list": MethodSpec(params=Empty, result=DevicesListResult, level="core"),
    "hal/devices/describe": MethodSpec(params=DescribeParams, result=DescribeResult, level="core"),
    "hal/read": MethodSpec(params=ReadParams, result=Reading, level="core"),
    "hal/readMany": MethodSpec(params=ReadManyParams, result=ReadManyResult, level="core"),
    "hal/write": MethodSpec(params=WriteParams, result=WriteDone | Pending, level="control"),
    "hal/dryRun": MethodSpec(params=DryRunParams, result=DryRunResult, level="control"),
    "hal/planCheck": MethodSpec(params=PlanCheckParams, result=PlanResult, level="control"),
    "hal/stop": MethodSpec(params=StopParams, result=StopResult, level="control"),
    "hal/action": MethodSpec(params=ActionParams, result=ActionDone | Pending, level="full"),
    "hal/confirmations/list": MethodSpec(params=ConfirmationsListParams, result=ConfirmationsListResult, level="full"),
    "hal/confirmations/approve": MethodSpec(params=ApproveParams, result=Decision, level="full", human_only=True),
    "hal/confirmations/reject": MethodSpec(
        params=RejectParams, result=ConfirmationRequest, level="full", human_only=True
    ),
    "hal/unlock": MethodSpec(params=UnlockParams, result=UnlockResult, level="control", human_only=True),
    "hal/routines/list": MethodSpec(params=Empty, result=RoutinesListResult, level="full"),
    "hal/routines/dryRun": MethodSpec(params=RoutineDryRunParams, result=PlanResult, level="full"),
    "hal/audit/query": MethodSpec(params=AuditQueryParams, result=AuditQueryResult, level="full"),
}
"""Every method the hub answers, with its params, result and conformance level."""

NOTIFICATIONS: Final[dict[str, tuple[type[Message], Conformance]]] = {
    "hal/value": (Reading, "core"),
    "hal/blocked": (BlockedParams, "control"),
    "hal/stopped": (StoppedParams, "control"),
    "hal/deviceAdded": (DeviceAddedParams, "core"),
    "hal/deviceRemoved": (DeviceRemovedParams, "core"),
    "hal/confirmationRequested": (ConfirmationRequestedParams, "full"),
}
"""Every notification the hub sends after `hal/initialized`, with its params and level."""

CLIENT_NOTIFICATIONS: Final[dict[str, type[Message]]] = {"hal/initialized": Empty, "hal/shutdown": Empty}
"""Notifications a client sends."""


def methods_for(level: Conformance) -> list[str]:
    """The methods a hub at `level` answers."""
    return [name for name, spec in METHODS.items() if LEVELS[spec.level] <= LEVELS[level]]


def notifications_for(level: Conformance) -> list[str]:
    """The notifications a hub at `level` sends."""
    return [name for name, (_, needed) in NOTIFICATIONS.items() if LEVELS[needed] <= LEVELS[level]]
