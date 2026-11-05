# Python library

`openhal.client` is the sync and async client of the hub's local API v1, used by scripts, the CLI and the MCP server. Safety checks run in the hub's kernel, and a blocked command comes back as a `Decision`.

```sh
uv pip install "halkit @ git+https://github.com/sohan-bhat/OpenHAL"
```

## Connect

```python
from openhal.client import connect

with connect() as hub:
    print(hub.status().devices, "devices")
    reading = hub.read("printer", "bed_temp")
    print(reading.value, reading.unit)
```

`connect()` calls `/v1/whoami` first, so a wrong address or token fails right away. `check=False` skips the call. The async client has the same methods.

```python
import asyncio
from openhal.client import aconnect

async def main() -> None:
    hub = await aconnect()
    async with hub:
        decision = await hub.write("printer", "bed_target", 70, "degC")
        print(decision.status, decision.message)

asyncio.run(main())
```

## Address and token

| Argument | Lookup when not given |
|---|---|
| `url` | `OPENHAL_URL`, then `api.host` and `api.port` from `config.yaml`, then `http://127.0.0.1:7420` |
| `token` | `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token` |
| `home` | `OPENHAL_HOME`, then `~/.openhal` |

Pass `use_human_token_file=False` for anything that acts for an agent, so the client never falls back to the human token file. The client uses no proxy environment variables, so a token never goes through a proxy.

## Exceptions

Every exception derives from `openhal.client.OpenHALError`, with `message`, `status_code` and `detail`.

| Exception | When |
|---|---|
| `HubNotRunning` | No hub at the address. The message names the command that starts the hub |
| `Unauthorized` | No token, or a token the hub doesn't accept. The message names the token's source |
| `NotFound` | Unknown device, channel, request, routine or session |
| `NotSupported` | The hub is older and has no such route. A subclass of `NotFound` |
| `Refused` | The hub blocked the request, such as an approval with an agent token or a request no longer pending |
| `BadRequest` | An unreadable request, or a wrong unlock phrase |
| `HubError` | The hub failed or timed out |

## Decisions

`write`, `action`, `approve` and every entry of `dry_run` return a `Decision`.

| Field | Meaning |
|---|---|
| `status` | `done`, `allowed` for a dry run, `blocked`, `pending` or `needs_confirmation`, `failed` |
| `code` | Stable block code, such as `above_max`, `rate_limited`, `interlock`, `not_permitted`, `stopped`, `misconfigured`, `queue_full` |
| `message` | What happened and the next step |
| `value`, `unit` | The value in the channel's unit |
| `limit` | The blocking limit, with its unit |
| `request_id` | Set when a person has to approve |

`decision.ok` is true for done and allowed, and `decision.pending` when the request is held for a person.

```python
decision = hub.write("printer", "extruder_target", 300, "degC")
if decision.status == "blocked":
    print(decision.code, decision.limit)
elif decision.pending:
    print("approve with openhal confirm approve", decision.request_id)
```

The request for a nozzle temperature of 300 degC prints `above_max {'max': 260.0, 'unit': 'degC'}`. A `cancel` of the print comes back pending, since a person approves each cancel.

## Images

An image channel, such as a camera frame, reads as an `Image` with `mime_type`, `bytes`, `width`, `height` and `content()`.

```python
frame = hub.read("printer-cam", "frame").value
print(frame.mime_type, frame.width, frame.height)
with open("frame.jpg", "wb") as out:
    out.write(frame.content())
```

In device views `content()` is empty, since views carry no pixels.

## Methods

Every method exists on `Client` and, as a coroutine, on `AsyncClient`.

### Hub and devices

| Method | Route |
|---|---|
| `status()` | `GET /v1/status` |
| `whoami()` | `GET /v1/whoami` |
| `devices()` | `GET /v1/devices` |
| `device(device_id)` | `GET /v1/devices/{id}` |
| `drivers()` | `GET /v1/drivers` |

### Reading and control

| Method | Route |
|---|---|
| `read(device, channel)` or `read("device.channel")` | `POST /v1/read` |
| `read_many(["device.channel", ("device", "channel")])` | `POST /v1/read_many` |
| `write(device, channel, value, unit=None)`, a number with its unit apart | `POST /v1/write` |
| `action(device, action, args=None, **kwargs)`, numbers as `{"value": 2, "unit": "s"}` | `POST /v1/action` |
| `dry_run([Write(...), Action(...), {...}])` | `POST /v1/dry_run` |
| `tighten(device, channel, min=None, max=None, rate=None)`, each a Quantity mapping | `POST /v1/tighten` |
| `risk(device)`, every channel's and action's level with the reasons | `GET /v1/devices/{id}/risk` |
| `set_risk(device, name, level, phrase=None)`, raising at once and lowering with the phrase or a person's approval | `POST /v1/risk` (human) |
| `stop(reason)` | `POST /v1/stop` |
| `unlock(phrase)` | `POST /v1/unlock` (human) |
| `ramp_to(device, channel, target, unit, interval_s=1.0, margin=0.9)` | several `POST /v1/write` |

`Write` and `Action` are the kernel's command models, exported from `openhal.client`. A dict with `device`, `channel` and `value`, or `device`, `action` and `args`, works too.

`ramp_to` moves a channel to a target in steps that each pass `max_change_per_s`, `interval_s` apart, each using `margin` of the allowed change. The kernel checks every step, the ramp stops at the first blocked step, and `ramp_to` returns every step's `Decision`. The LED strip from [Add a device](../guide/tutorials/add-a-device.md) changes `brightness` by at most 40 %/s.

```python
for decision in hub.ramp_to("led-strip", "brightness", 80, "%"):
    print(decision.status, decision.message)
```

### Find, wait, sample and runs

| Method | Route |
|---|---|
| `find(text=None, unit=None, kind=None, hazard=None, connected=None, limit=50)` | `GET /v1/find` |
| `wait_until(condition, timeout_s=30.0, interval_s=1.0)` | `POST /v1/wait_until` |
| `sample(targets, duration_s=, interval_s=1.0)` | `POST /v1/sample` |
| `run_steps(steps, repeat=1, wait_s=5.0)` | `POST /v1/runs` |
| `run(run_id, wait_s=0.0, last=50)` | `GET /v1/runs/{id}` |
| `runs()` | `GET /v1/runs` |
| `cancel_run(run_id)` | `POST /v1/runs/{id}/cancel` |
| `run_caps()` | `GET /v1/runs/caps` |
| `set_run_caps(max_steps=None, max_seconds=None, per_agent=None, phrase=None)` | `POST /v1/runs/caps` (human) |

`find` searches every device and returns `device.channel` and `device.action` targets with units, limits and latest values. Text also matches what a unit measures, so `find("current")` finds a channel in A, and `unit="degC"` finds every temperature channel.

```python
for match in hub.find("current", kind="readable").matches:
    print(match.target, match.value, match.unit)
```

`wait_until` reads until the condition holds or the timeout passes. `sample` reads channels at an interval and returns each series with min, max and mean. Every reading goes through the kernel into the audit log.

```python
result = hub.wait_until("led-strip.current_draw < 1 A", timeout_s=30)
print(result.held, result.readings[0].value)
```

`run_steps` checks the steps as a plan, then runs the steps in order. A step is a `Write`, an `Action` or a dict whose `kind` is `read`, `write`, `action`, `wait` or `wait_until`, and `increment` adds that much on each repeat. The kernel checks each command, and the run stops at the first step that isn't done. A step that needs a person ends the run with `request_id`. The reply comes when the run ends or after `wait_s`, and `run()` and `cancel_run()` follow a longer run.

```python
run = hub.run_steps(
    [
        {"kind": "write", "device": "led-strip", "channel": "power", "value": True},
        {"kind": "wait", "seconds": 0.5},
        {"kind": "write", "device": "led-strip", "channel": "power", "value": False},
        {"kind": "wait", "seconds": 0.5},
    ],
    repeat=3,
)
print(run.status, run.message)
```

`run_caps()` shows the caps on steps per run, seconds per run, wait or sample, and how many one token has at once. Only a human token changes the caps, with `phrase="confirm"` to raise one.

### Confirmations

| Method | Route |
|---|---|
| `confirmations(include_done=False)` | `GET /v1/confirmations` |
| `confirmation(request_id)` | `GET /v1/confirmations/{id}` |
| `approve(request_id)` | `POST /v1/confirmations/{id}/approve` (human) |
| `reject(request_id, reason="")` | `POST /v1/confirmations/{id}/reject` (human) |

The library never prompts. A script with the human token can approve, so the human token file is readable by its owner only. The CLI adds the terminal and typed phrase checks of ADR 0012.

### Audit log

| Method | Route |
|---|---|
| `audit(device=None, status=None, event=None, since=0, limit=200)` | `GET /v1/audit` |
| `verify_audit()` | `GET /v1/audit/verify` |

### Discovery

| Method | Route |
|---|---|
| `discover(drivers=None)` | `POST /v1/discover` |
| `unknown_devices()` | `GET /v1/discover/unknown` |

### Routines

| Method | Route |
|---|---|
| `routines()` | `GET /v1/routines` |
| `routine(id)` | `GET /v1/routines/{id}` |
| `create_routine(id, source, kind="yaml")` | `POST /v1/routines`, always disabled |
| `routine_dry_run(id)` | `POST /v1/routines/{id}/dry_run` |
| `enable_routine(id)` | `POST /v1/routines/{id}/enable` (human, or an agent under ADR 0007's opt-in) |
| `disable_routine(id)` | `POST /v1/routines/{id}/disable` |
| `run_routine(id)` | `POST /v1/routines/{id}/run` (human) |
| `delete_routine(id)` | `DELETE /v1/routines/{id}` (human) |
| `approve_routine(id, device)` | `POST /v1/routines/{id}/approve` (human) |

`Routine.source` is wrapped in a device-data block for models, and `Routine.source_raw` is the plain text.

### Driver writer

| Method | Route |
|---|---|
| `start_writer(unknown_id=, driver=, params=, sketch_path=, manual_text=)` | `POST /v1/writer/sessions` |
| `writer_session(id)` | `GET /v1/writer/sessions/{id}` |
| `propose(id, draft_yaml)` | `POST /v1/writer/sessions/{id}/propose` |
| `interview(id)` | `GET /v1/writer/sessions/{id}/interview` |
| `answer(id, answers)` | `POST /v1/writer/sessions/{id}/answers` (human) |
| `finish(id, save_as=None)` | `POST /v1/writer/sessions/{id}/finish` (human) |
| `test_plan(id)` | `GET /v1/writer/sessions/{id}/test_plan` |

### Tokens and pairing

| Method | Route |
|---|---|
| `new_pairing_code()` | `POST /v1/pair/code` (human) |
| `pair(code)` | `POST /v1/pair` |
| `tokens()` | `GET /v1/tokens` (human) |
| `create_token(name, kind="agent", scope="read")` | `POST /v1/tokens` (human) |
| `revoke_token(token_id)` | `DELETE /v1/tokens/{id}` (human) |

### Live events

`AsyncClient.events()` yields the hub's live events from `/v1/live` as dicts, typed `hello`, `reading`, `state`, `audit` or `watchdog`.

```python
async with AsyncClient() as hub:
    async for event in hub.events():
        if event["type"] == "reading":
            print(event["device"], event["channel"], event["value"], event["unit"])
```

### Any route

`client.call(Call(...))` sends one request built with `openhal.client.calls`, for routes newer than the methods.

## Models

Responses are pydantic models from `openhal.client.models` that keep unknown fields, so a newer hub works with an older client. `at`, `started_at` and `finished_at` are Unix seconds. A confirmation request's `created_at` and `expires_at` use the hub's monotonic clock and only compare with each other.
