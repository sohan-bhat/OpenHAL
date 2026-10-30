# Python library

`openhal.client` is a sync and an async client of the hub's local API v1, and scripts, the CLI and the MCP server all use the client. The client runs no safety checks, because the hub's kernel checks every command, and a blocked command comes back as a `Decision` rather than as an exception.

```sh
uv pip install "openhal-hub @ git+https://github.com/sohan-bhat/OpenHAL"
```

The install puts the client in the current environment, so your own scripts can import the client.

## Connect

```python
from openhal.client import connect

with connect() as hub:
    print(hub.status().devices, "devices")
    reading = hub.read("printer", "bed_temp")
    print(reading.value, reading.unit)
```

`connect()` calls `/v1/whoami` on the hub straight away, so a wrong address or token fails at once with a clear exception, and `check=False` skips that call.

The async client has the same methods.

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
| `token` | `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token` (default `~/.openhal/human.token`) |
| `home` | `OPENHAL_HOME`, then `~/.openhal` |

`Client(..., use_human_token_file=False)` never falls back to the human token file, so pass `use_human_token_file=False` for anything that acts for an agent. The client doesn't use proxy environment variables, so a token is never sent through a proxy.

## Exceptions

All of these exceptions derive from `openhal.client.OpenHALError`, which has `message`, `status_code` and `detail`.

| Exception | When |
|---|---|
| `HubNotRunning` | No hub responds at the hub address. The message names the command that starts the hub |
| `Unauthorized` | No token, or the hub doesn't accept the token. The message names where the token came from |
| `NotFound` | Unknown device, channel, request, routine or session |
| `NotSupported` | The hub is older and has no such route. A subclass of `NotFound` |
| `Refused` | The hub blocked the request, for example an approval sent with an agent token, or a request that is no longer pending |
| `BadRequest` | The hub could not read the request, or a wrong unlock phrase |
| `HubError` | The hub failed or timed out |

## Decisions

`write`, `action`, `approve` and every entry of `dry_run` return a `Decision`.

| Field | Meaning |
|---|---|
| `status` | `done`, `allowed` (dry run), `blocked`, `pending` or `needs_confirmation`, `failed` |
| `code` | Stable block code, for example `above_max`, `rate_limited`, `interlock`, `not_permitted`, `stopped`, `misconfigured`, `queue_full` |
| `message` | What happened and what to do next |
| `value`, `unit` | The value in the channel's unit |
| `limit` | The limit that blocked it, with its unit |
| `request_id` | Set when a person has to approve |

`decision.ok` is true for done and allowed, and `decision.pending` is true when the hub holds the request for a person's approval.

```python
decision = hub.write("printer", "extruder_target", 300, "degC")
if decision.status == "blocked":
    print(decision.code, decision.limit)
elif decision.pending:
    print("approve with openhal confirm approve", decision.request_id)
```

The request for a nozzle temperature of 300 degC prints `above_max {'max': 260.0, 'unit': 'degC'}`. Because a person approves each cancel, a `cancel` of the print comes back pending.

## Images

An image channel, such as a camera frame, reads as an `Image` with `mime_type`, `bytes`, `width` and `height`. `content()` gives the image itself.

```python
frame = hub.read("printer-cam", "frame").value
print(frame.mime_type, frame.width, frame.height)
with open("frame.jpg", "wb") as out:
    out.write(frame.content())
```

Device views carry the same object without the pixels, so `content()` is empty there.

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
| `stop(reason)` | `POST /v1/stop` |
| `unlock(phrase)` | `POST /v1/unlock` (human) |
| `ramp_to(device, channel, target, unit, interval_s=1.0, margin=0.9)` | several `POST /v1/write` |

`Write` and `Action` are the kernel's command models, exported from `openhal.client`. A plain dict with `device` and `channel` and `value`, or `device` and `action` and `args`, works too.

`ramp_to` moves a channel to a target in steps that each pass its `max_change_per_s`, waiting `interval_s` before each step, with `margin` of the allowed change per step. The kernel still checks every step, the ramp stops at the first step the kernel blocks, and `ramp_to` returns the `Decision` of every step. The LED strip from [Add a device](../guide/tutorials/add-a-device.md) limits `brightness` to a change of at most 40 %/s.

```python
for decision in hub.ramp_to("led-strip", "brightness", 80, "%"):
    print(decision.status, decision.message)
```

### Confirmations

| Method | Route |
|---|---|
| `confirmations(include_done=False)` | `GET /v1/confirmations` |
| `confirmation(request_id)` | `GET /v1/confirmations/{id}` |
| `approve(request_id)` | `POST /v1/confirmations/{id}/approve` (human) |
| `reject(request_id, reason="")` | `POST /v1/confirmations/{id}/reject` (human) |

The library never prompts, and because a script with the human token can approve, the human token file is readable by its owner only. The CLI adds the terminal and typed phrase checks of ADR 0012.

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

`AsyncClient.events()` yields the hub's live events from `/v1/live` (`hello`, `reading`, `state`, `audit`, `watchdog`) as dicts.

```python
async with AsyncClient() as hub:
    async for event in hub.events():
        if event["type"] == "reading":
            print(event["device"], event["channel"], event["value"], event["unit"])
```

### Any route

`client.call(Call(...))` sends one request built with `openhal.client.calls`, for routes newer than the client's methods.

## Models

Every response is a pydantic model from `openhal.client.models` that keeps unknown fields, so a newer hub does not break an older client. Timestamps named `at`, `started_at` and `finished_at` are Unix seconds. The `created_at` and `expires_at` of a confirmation request use the hub's monotonic clock and only mean something relative to each other.
