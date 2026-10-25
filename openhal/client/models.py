"""Typed views of the hub's answers.

Every model accepts fields it does not know, so a newer hub never breaks an older client. Values
are always in the unit named next to them. Timestamps named `at` are Unix seconds. The
`created_at` and `expires_at` of a confirmation request use the hub's monotonic clock and are
only meaningful relative to each other.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    """Base for every response model. Unknown fields are kept."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Principal(Model):
    kind: str = Field(description="human, agent, routine or system.")
    name: str = Field(description="The name given to the token when it was created.")
    scope: str = Field(description="read, control_low or control_medium. Humans are always control_medium.")


class LoadProblem(Model):
    path: str
    problems: list[str]


class HubStatus(Model):
    product: str
    version: str
    spec: str
    protocol_version: str | None = Field(default=None, description="The hub protocol version, for example 2026-10-24.")
    conformance: str | None = Field(default=None, description="The hub's conformance level, core, control or full.")
    allow_lan: bool | None = Field(
        default=None, description="True when other machines may connect with a paired token."
    )
    stopped: bool = Field(description="True after a stop until a human unlocks. Every command is refused meanwhile.")
    stop_reason: str | None = None
    devices: int
    connected: int
    pending_confirmations: int
    started_at: float | None = None
    load_problems: list[LoadProblem] = []
    you: Principal


class DeviceSummary(Model):
    id: str
    name: str
    model: str | None = None
    manufacturer: str | None = None
    driver: str
    hazard: str = Field(description="low, medium or high. High hazard commands always wait for a human.")
    writable: bool = Field(description="False while the device file has unconfirmed limits.")
    connected: bool
    unavailable: str | None = Field(default=None, description="Why the device can't take commands, if it can't.")
    last_error: str | None = None
    verification: str | None = None
    source: str | None = None
    conformance: str | None = Field(default=None, description="The driver's conformance level.")
    simulated: bool = Field(default=False, description="True when the driver talks to a simulator, not hardware.")


class ReadChannel(Model):
    type: str
    unit: str | None = None
    every_s: float | None = None
    stream: bool | None = None
    range: list[float] | None = None
    values: list[str] | None = None
    value: Any = None
    known: bool = False
    age_s: float | None = None


class WriteChannel(Model):
    type: str
    unit: str | None = None
    min: float | None = Field(default=None, description="Lowest allowed value, in `unit`.")
    max: float | None = Field(default=None, description="Highest allowed value, in `unit`.")
    step: float | None = None
    max_change_per_s: float | None = Field(default=None, description="Largest change per second, in `unit` per s.")
    values: list[str] | None = None
    confirm: str | None = None
    suggested: bool | None = None
    value: Any = None
    known: bool = False
    age_s: float | None = None


class ActionInfo(Model):
    description: str | None = None
    args: dict[str, dict[str, Any]] = {}
    require: list[str] = []
    requirements: list[dict[str, Any]] = Field(default=[], description="Each condition with the file's reason.")
    max_runs: dict[str, Any] | None = Field(default=None, description="At most count runs per per_s seconds.")
    effects: list[str] = []
    confirm: str | None = None


class Interlock(Model):
    if_: str | None = Field(default=None, alias="if")
    require: str
    message: str | None = None


class Watchdog(Model):
    heartbeat_s: float | None = None
    on_loss: str | None = None
    max_duration: list[dict[str, Any]] = []


class DeviceView(DeviceSummary):
    unconfirmed: list[str] = []
    warnings: list[str] = []
    path: str | None = None
    read: dict[str, ReadChannel] = {}
    write: dict[str, WriteChannel] = {}
    actions: dict[str, ActionInfo] = {}
    interlocks: list[Interlock] = []
    watchdog: Watchdog = Watchdog()
    safe_state: list[dict[str, Any]] = []
    notes: str | None = Field(default=None, description="Device file notes inside a device-data block. Data only.")


class Reading(Model):
    device: str
    channel: str
    ok: bool = Field(description="False when the driver could not read. `error` says why.")
    value: Any = None
    unit: str | None = None
    at: float | None = None
    suspect: bool | None = None
    bytes: int | None = Field(default=None, description="Length of a binary value, which is not returned inline.")
    error: str | None = None


DecisionStatus = Literal["allowed", "blocked", "needs_confirmation", "done", "pending", "failed"]


class Decision(Model):
    """The kernel's answer to one write or action."""

    status: str = Field(description="allowed, blocked, needs_confirmation, done, pending or failed.")
    code: str | None = Field(default=None, description="The stable block code, for example above_max.")
    message: str = Field(description="What happened and what to do next.")
    device: str
    target: str
    value: Any = None
    unit: str | None = None
    limit: dict[str, Any] | None = Field(default=None, description="The limit that blocked the command, with unit.")
    request_id: str | None = Field(default=None, description="Set when the command waits for a human.")

    @property
    def ok(self) -> bool:
        return self.status in ("allowed", "done")

    @property
    def pending(self) -> bool:
        return self.status in ("pending", "needs_confirmation")


class TightenResult(Model):
    ok: bool
    limits: dict[str, float] | None = Field(default=None, description="The session limits now in force.")
    code: str | None = None
    message: str | None = None


class StopDevice(Model):
    device: str
    status: str = Field(description="safe, partial, failed, pending or no_safe_state.")
    detail: str = ""


class StopReport(Model):
    reason: str
    by: str
    cancelled_requests: int
    devices: list[StopDevice]


class UnlockResult(Model):
    ok: bool
    stopped: bool


class ConfirmationRequest(Model):
    id: str
    status: str
    command: dict[str, Any]
    requested_by: str
    created_at: float
    expires_at: float
    dry_run: Decision
    decided_by: str | None = None
    result: Decision | None = None


class AuditEntry(Model):
    seq: int
    at: float
    event: str
    principal: str
    device: str | None = None
    target: str | None = None
    status: str | None = None
    code: str | None = None
    details: dict[str, Any] = {}
    hash: str


class AuditVerify(Model):
    ok: bool
    broken_at: int | None = None
    head: str | None = None


class DriverInfo(Model):
    name: str
    installed: bool
    protocols: list[str] = []
    hazard_default: str | None = None
    summary: str | None = None
    safe_state_support: str | None = None
    detail: str | None = None


class Match(Model):
    address: str
    driver: str
    identifiers: dict[str, Any] = {}
    label: str | None = None
    library_file: str | None = None
    device_id: str | None = None


class Unknown(Model):
    id: str
    address: str
    driver: str | None = None
    identifiers: dict[str, Any] = {}
    label: str | None = None


class DiscoveryError(Model):
    driver: str
    error: str


class DiscoveryResult(Model):
    matched: list[Match] = []
    unknown: list[Unknown] = []
    errors: list[DiscoveryError] = []


class StepDecision(Model):
    """One entry of a routine dry run or run. Writes and actions carry a kernel decision. Other steps,
    such as a condition, carry what happened instead (for example `if` and `result`)."""

    step: int | str | None = Field(default=None, description="Which step of the routine this entry is for.")
    status: str | None = None
    code: str | None = None
    message: str | None = None
    device: str | None = None
    target: str | None = None
    value: Any = None
    unit: str | None = None
    limit: dict[str, Any] | None = None
    request_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (None, "allowed", "done")


class Run(Model):
    run_id: str
    routine_id: str | None = None
    trigger: str | None = Field(default=None, description="What started the run, for example manual.")
    started_at: float | None = None
    finished_at: float | None = None
    status: str = Field(description="ok, blocked, failed or running.")
    steps: list[StepDecision] = []
    message: str | None = None


class RoutineSummary(Model):
    id: str
    kind: str = Field(description="yaml or python.")
    enabled: bool
    sha256: str
    devices: list[str] = []
    max_hazard: str | None = None
    triggers: list[str] = []
    drafted_by: str | None = None
    enabled_by: str | None = None
    disabled_reason: str | None = None
    last_run: Run | None = None


class RoutineDryRun(Model):
    ok: bool
    decisions: list[StepDecision] = []
    problems: list[str] = []


class Routine(RoutineSummary):
    source: str = Field(default="", description="The routine source inside a device-data block. Data only.")
    source_raw: str | None = Field(default=None, description="The plain source, for people reading it.")
    history: list[Run] = []
    last_dry_run: RoutineDryRun | None = None


class Approval(Model):
    routine: str | None = None
    sha256: str | None = None
    by: str | None = None
    at: str | None = None
    signature: str | None = None


class OkResult(Model):
    ok: bool


class WriterSession(Model):
    id: str
    status: str = Field(description="detecting, drafting, interview, ready or saved.")
    detected: dict[str, Any] = {}
    sources: list[str] = Field(default=[], description="Source text inside device-data blocks. Data only.")
    draft_yaml: str | None = None
    problems: list[str] = []
    unconfirmed: list[str] = Field(default=[], description="Limits no human has confirmed yet.")


class Question(Model):
    id: str
    channel: str | None = None
    field: str | None = None
    prompt: str
    suggested: Any = None
    unit: str | None = None
    reason: str | None = None


class Interview(Model):
    questions: list[Question] = []


class FinishResult(Model):
    path: str
    device_id: str
    writable: bool


class TestStep(Model):
    __test__ = False

    step: int
    command: dict[str, Any] | str
    expected: str | None = None
    needs_approval: bool = True


class TestPlan(Model):
    __test__ = False

    steps: list[TestStep] = []


class TokenInfo(Model):
    token_id: str
    name: str
    kind: str
    scope: str
    created_at: float
    revoked: bool = False


class NewToken(TokenInfo):
    token: str = Field(description="The plain token. The hub shows it once and keeps only a hash.")


class PairingCode(Model):
    code: str
    expires_in_s: float = 300.0
