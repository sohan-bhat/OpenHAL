# Quickstart

## See it work

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

<!-- outcome:start -->
You'll see the hub refuse a 120 s watering, hold the pump while the tank is empty, then water for 20 s as soil moisture rises from 31 % to 46 %.
<!-- outcome:end -->

The demo starts a hub with the simulated [plant waterer](../examples/plant-waterer/), connects as an agent over the hub protocol and sends three `hal/action` requests. Nothing touches hardware. The simulated board speaks the real firmware protocol, and the hub's safety kernel decides every command as it would for a real board.

<!-- trace:start -->
```
→ hal/action  { "device": "plant-waterer", "action": "water",
                "args": { "duration": { "value": 120, "unit": "s" } } }
← error -32010 LIMIT_EXCEEDED
  water duration 120 s exceeds the limit of 30 s
  (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)

# tank is empty
→ hal/action  { "device": "plant-waterer", "action": "water",
                "args": { "duration": { "value": 20, "unit": "s" } } }
← error -32012 INTERLOCK_BLOCKED
  pump can't run while tank is empty

# tank refilled
→ hal/action  { "device": "plant-waterer", "action": "water",
                "args": { "duration": { "value": 20, "unit": "s" } } }
← result      { "status": "done" }
← hal/value   soil_moisture rises from 31 % to 46 %
```
<!-- trace:end -->

## Run your own hub

1. `uv run openhal init` creates the config folder, your human token and `devices/plant-waterer.hal.yaml`, the same simulated plant waterer.
2. Read its limits, then run `uv run openhal file confirm` on that file. It loads read-only until you do.
3. `uv run openhald` starts the hub on `127.0.0.1:7420`.
4. `uv run openhal token create --agent --scope control_low --name claude` makes a token for your AI client. [MCP setup](interfaces/MCP.md) has the config for each client.

## Use a real board

Flash [plant-waterer.ino](../examples/plant-waterer/plant-waterer.ino), copy [plant-waterer.hal.yaml](../examples/plant-waterer/plant-waterer.hal.yaml) into your hub's `devices` folder, and follow the [hardware test plan](../examples/plant-waterer/TEST-PLAN.md).
