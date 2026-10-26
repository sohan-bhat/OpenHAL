# Quickstart

## See it work

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

<!-- outcome:start -->
You'll see the agent warm the bed from 60 °C to 70 °C, have a 300 °C nozzle refused at the 260 °C limit, pause the print when it comes loose and wait for a person to approve the cancel.
<!-- outcome:end -->

The demo starts a hub with a simulated Klipper [printer and its camera](../examples/print-babysitter/), connects as an agent over the hub protocol and keeps an eye on a print. It reads camera frames, warms the bed, asks for a nozzle over the limit, pauses the print when it comes loose and asks to cancel. Nothing touches hardware. The printer runs on a Moonraker simulator, the camera frames are line drawings, and the hub's safety kernel decides every command as it would for a real printer.

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

→ hal/write   { "device": "printer", "channel": "extruder_target",
                "value": 300, "unit": "degC" }
← error -32010 LIMIT_EXCEEDED
  extruder_target 300 degC exceeds the limit of 260 degC
  (printer.hal.yaml, confirmed by owner 2026-10-24)

# later
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
```
<!-- trace:end -->

## Run your own hub

1. `uv run openhal init` creates the config folder, your human token and `devices/plant-waterer.hal.yaml`, the same simulated plant waterer.
2. Read its limits, then run `uv run openhal file confirm` on that file. It loads read-only until you do.
3. `uv run openhald` starts the hub on `127.0.0.1:7420`.
4. `uv run openhal token create --agent --scope control_low --name claude` makes a token for your agent. [MCP setup](interfaces/MCP.md) has the config for each client.

## Use a real printer

Copy [printer.hal.yaml](../examples/print-babysitter/printer.hal.yaml) and [printer-cam.hal.yaml](../examples/print-babysitter/printer-cam.hal.yaml) into your hub's `devices` folder and set your printer's host name in both. Remove the `confirmed` line, read every limit, then run `uv run openhal file confirm` on each file. The [example's README](../examples/print-babysitter/) explains each limit.

## Use a real board

Flash [plant-waterer.ino](../examples/plant-waterer/plant-waterer.ino), copy [plant-waterer.hal.yaml](../examples/plant-waterer/plant-waterer.hal.yaml) into your hub's `devices` folder, and follow the [hardware test plan](../examples/plant-waterer/TEST-PLAN.md).
