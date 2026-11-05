# FAQ

## Is OpenHAL a standard?

No. OpenHAL is an open protocol with a versioned specification, now at v0.1, and anyone may implement a hub, client or driver.

## Is OpenHAL a safety system?

No. The hub checks every command against limits a person set and stops everything on request, but firmware still controls each device, so a motor that stops responding on the serial port keeps running. Keep your e-stops, enclosures and hardware interlocks.

## Which AI clients work with OpenHAL?

Any MCP client over stdio, including Claude Desktop, Claude Code and Cursor. Other clients call the JSON-RPC methods over a WebSocket or stdio, and scripts use the CLI or the Python SDK. Every client reaches the same kernel.

## Does the model decide what is safe?

No. The kernel is plain code in the hub with no model, so the same request against the same state always gets the same result.

## Can an agent change a limit?

An agent may tighten a limit for the agent's own session. Loosening a limit, confirming a device file, approving a request and lifting a stop take a person with the human token.

## What happens when a sensor stops responding?

The value becomes unknown after a short time, and an unknown value counts as unsafe. Interlocks on the value block commands, and rate limits block changes until a fresh reading arrives. If the device drops off, the hub applies the safe state where the device's protocol allows.

## Does OpenHAL need firmware on my device?

Not for devices with an existing interface, such as SCPI bench instruments, Klipper printers or Home Assistant entities, and [Drivers](/drivers/) lists the driver for each. On boards you program yourself, the OpenHAL Arduino library adds a self-description and moves the board to a safe state when the hub's heartbeat stops.

## Does anything leave my machine?

No. The hub binds to 127.0.0.1, sends no telemetry and connects only to the devices and bridges you configured. Other machines need `api.allow_lan` and a paired token.

## How does OpenHAL relate to MHS?

Anthropic's Model Hardware Standard is a limited research preview for invited labs. OpenHAL is an independent open protocol, not affiliated with Anthropic or MHS, and the project plans to stay compatible with MHS. The [MHS mapping](../../spec/MHS-MAPPING.md) lines device files up with what MHS has published.

## Is the browser demo the real kernel?

No. The playground runs a TypeScript port of the kernel's checks, and a test requires the port and the Python kernel to give the same status, code and message. The port never protects hardware.

## What does the device library contain?

One CC0 device file per model, each with a verification badge. Every file is unverified today, because no file has been tested on a real device yet. [Add a device](tutorials/add-a-device.md) shows how to contribute a file.
