# Quickstart

## See the demo

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

<!-- outcome:start -->
You'll see the agent raise the bed target from 60 °C to 70 °C, have a request for a nozzle temperature of 300 °C blocked at the nozzle limit of 260 °C and pause the print when the camera shows the print has come loose. The owner then approves the cancel, and the printer's state becomes cancelled.
<!-- outcome:end -->

The demo starts a hub with a simulated Klipper [printer and its camera](../examples/print-babysitter/) and connects an agent over the hub protocol to watch a print. The agent reads camera frames, raises the bed target, sends a request for a nozzle temperature above the nozzle limit, which the hub blocks, pauses the print and sends a request to cancel the print. Because a cancel can't be undone, the hub holds the cancel request until the owner approves the request with the human token over the same protocol, well inside the hub's five minute window. The demo sends nothing to hardware, because the printer runs on a Moonraker simulator and the camera frames are line drawings, but the hub's safety kernel checks every command exactly as the kernel would for a real printer.

<!-- trace:start -->
The agent reads a frame from the printer's camera to check how the print is starting.

```
→ hal/read    { "device": "printer-cam", "channel": "frame" }
← result      { "value": { "mimeType": "image/jpeg", "bytes": 19409,
                "width": 640, "height": 480, "data": "…" } }
```

A corner of the print is lifting off the bed, so the agent sends a request to raise the bed target. The new target is inside the bed limit, so the hub passes the request to the printer.

```
→ hal/write   { "device": "printer", "channel": "bed_target",
                "value": 70, "unit": "degC" }
← result      { "status": "done" }
```

A hotter nozzle might help the corner stick, so the agent sends a request for a higher nozzle temperature. The request is above the nozzle limit, so the hub blocks the request.

```
→ hal/write   { "device": "printer", "channel": "extruder_target",
                "value": 300, "unit": "degC" }
← error -32010 LIMIT_EXCEEDED
  extruder_target 300 degC exceeds the limit of 260 degC
  (printer.hal.yaml, confirmed by owner 2026-10-24)
```

Later the agent reads another frame to check the print again.

```
→ hal/read    { "device": "printer-cam", "channel": "frame" }
← result      { "value": { "mimeType": "image/jpeg", "bytes": 23567,
                "width": 640, "height": 480, "data": "…" } }
```

The print has come loose, so the agent pauses the print.

```
→ hal/action  { "device": "printer", "action": "pause" }
← result      { "status": "done" }
```

The agent sends a request to cancel the print. A cancel can't be undone, so the hub holds the request until the owner approves the request.

```
→ hal/action  { "device": "printer", "action": "cancel" }
← result      { "status": "pending", "requestId": "REQUEST_ID",
                "expiresInS": 300 }
```

The owner approves the cancel with the human token over the same protocol, and the cancel runs.

```
→ hal/confirmations/approve { "requestId": "REQUEST_ID" }
← result      { "status": "done" }
```
<!-- trace:end -->

The demo ends with the hub's audit log, newest first. `TIME` stands in for the time of each entry.

<!-- audit:start -->
```
seq  time  event    who           target                   status   message
13   TIME  action   agent:claude  printer.cancel           done     Done. cancel ran.
12   TIME  confirm  human:owner   printer.cancel           done
11   TIME  action   agent:claude  printer.cancel           pending  Held until a human approves action:cancel on printer.
10   TIME  action   agent:claude  printer.pause            done     Done. pause ran.
9    TIME  read     agent:claude  printer-cam.frame        done
8    TIME  write    agent:claude  printer.extruder_target  blocked  Blocked. The extruder_target limit is 260 degC (max). Requested 300 degC.
7    TIME  write    agent:claude  printer.bed_target       done     Done. bed_target is now 70 degC.
6    TIME  read     agent:claude  printer-cam.frame        done
```

6 requests, 1 blocked, 1 confirmed by a person.
<!-- audit:end -->

## Run your own hub

1. `uv run openhal init` creates the config folder, your human token and `devices/plant-waterer.hal.yaml`, the simulated Arduino plant waterer, and looks for your devices. For each device init adds, you answer each limit once at the terminal, where Enter keeps the suggestion, and then you type `confirm`. The device file is saved with every limit confirmed, and nothing needs editing by hand.
2. Run `uv run openhal file confirm` on the plant waterer's file, which confirms the sample's limits the same way.
3. `uv run openhal start` starts OpenHAL on `127.0.0.1:7420`. A running OpenHAL loads each confirmed file at once, so a confirm never needs a restart.
4. When init finds Claude Code, Claude Desktop or Cursor, you can add OpenHAL to each one with a token for your agent. [MCP setup](interfaces/MCP.md) has the config for any other client.

To raise a limit later, run `uv run openhal limits set DEVICE.CHANNEL --max VALUE` and type `confirm`. A narrower limit applies at once. A wider limit asked for from a script or an agent waits for you in `openhal confirm list` and in the Inspector.

## Use a real printer

Copy [printer.hal.yaml](../examples/print-babysitter/printer.hal.yaml) and [printer-cam.hal.yaml](../examples/print-babysitter/printer-cam.hal.yaml) into your hub's `devices` folder and set your printer's host name in both. Remove the `confirmed` line, then run `uv run openhal file confirm` on each file, which shows every limit before you type `confirm`. The [example's README](../examples/print-babysitter/) explains each limit.

## Use a real board

Flash [plant-waterer.ino](../examples/plant-waterer/plant-waterer.ino), copy [plant-waterer.hal.yaml](../examples/plant-waterer/plant-waterer.hal.yaml) into your hub's `devices` folder, and follow the [hardware test plan](../examples/plant-waterer/TEST-PLAN.md).
