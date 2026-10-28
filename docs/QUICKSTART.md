# Quickstart

## See the demo

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

<!-- outcome:start -->
You'll see the agent raise the bed target from 60 °C to 70 °C, have a request for a nozzle temperature of 300 °C refused at the nozzle limit of 260 °C and pause the print when the camera shows the print has come loose. The owner then approves the cancel, and the printer's state becomes cancelled.
<!-- outcome:end -->

The demo starts a hub with a simulated Klipper [printer and its camera](../examples/print-babysitter/) and connects an agent over the hub protocol to watch a print. The agent reads camera frames, raises the bed target, requests a nozzle temperature above the nozzle limit, which the hub refuses, pauses the print and requests a cancel. Because a cancel can't be undone, the cancel waits until the owner approves the request with the human token over the same protocol, well inside the hub's five minute window. The demo sends nothing to hardware, because the printer runs on a Moonraker simulator and the camera frames are line drawings, but the hub's safety kernel checks every command exactly as the kernel would for a real printer.

<!-- trace:start -->
```
# the agent checks the first layer
→ hal/read    { "device": "printer-cam", "channel": "frame" }
← result      { "value": { "mimeType": "image/jpeg", "bytes": 19409,
                "width": 640, "height": 480, "data": "…" } }

# a corner of the first layer is lifting
→ hal/write   { "device": "printer", "channel": "bed_target",
                "value": 70, "unit": "degC" }
← result      { "status": "done" }

# a hotter nozzle might help the corner stick
→ hal/write   { "device": "printer", "channel": "extruder_target",
                "value": 300, "unit": "degC" }
← error -32010 LIMIT_EXCEEDED
  extruder_target 300 degC exceeds the limit of 260 degC
  (printer.hal.yaml, confirmed by owner 2026-10-24)

# later the agent checks the print again
→ hal/read    { "device": "printer-cam", "channel": "frame" }
← result      { "value": { "mimeType": "image/jpeg", "bytes": 23567,
                "width": 640, "height": 480, "data": "…" } }

# the print has come loose
→ hal/action  { "device": "printer", "action": "pause" }
← result      { "status": "done" }

# cancelling can't be undone
→ hal/action  { "device": "printer", "action": "cancel" }
← result      { "status": "pending", "requestId": "REQUEST_ID",
                "expiresInS": 300 }

# the owner approves the cancel
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
11   TIME  action   agent:claude  printer.cancel           pending  Waiting for a human to approve action:cancel on printer.
10   TIME  action   agent:claude  printer.pause            done     Done. pause ran.
9    TIME  read     agent:claude  printer-cam.frame        done
8    TIME  write    agent:claude  printer.extruder_target  blocked  Blocked. The extruder_target limit is 260 degC (max). Asked for 300 degC.
7    TIME  write    agent:claude  printer.bed_target       done     Done. bed_target is now 70 degC.
6    TIME  read     agent:claude  printer-cam.frame        done
```

6 requests, 1 refused, 1 confirmed by a person.
<!-- audit:end -->

## Run your own hub

1. `uv run openhal init` creates the config folder, your human token and `devices/plant-waterer.hal.yaml`, the simulated Arduino plant waterer.
2. Read the file's limits, then run `uv run openhal file confirm` on the file. The hub loads the file read-only until you confirm the limits.
3. `uv run openhald` starts the hub on `127.0.0.1:7420`.
4. `uv run openhal token create --agent --scope control_low --name claude` makes a token for your agent. [MCP setup](interfaces/MCP.md) has the config for each client.

## Use a real printer

Copy [printer.hal.yaml](../examples/print-babysitter/printer.hal.yaml) and [printer-cam.hal.yaml](../examples/print-babysitter/printer-cam.hal.yaml) into your hub's `devices` folder and set your printer's host name in both. Remove the `confirmed` line, read every limit, then run `uv run openhal file confirm` on each file. The [example's README](../examples/print-babysitter/) explains each limit.

## Use a real board

Flash [plant-waterer.ino](../examples/plant-waterer/plant-waterer.ino), copy [plant-waterer.hal.yaml](../examples/plant-waterer/plant-waterer.hal.yaml) into your hub's `devices` folder, and follow the [hardware test plan](../examples/plant-waterer/TEST-PLAN.md).
