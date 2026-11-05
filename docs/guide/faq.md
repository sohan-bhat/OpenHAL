# FAQ

## Is OpenHAL a standard?

No. OpenHAL is an open protocol with a versioned specification, now v0.1, that anyone may implement.

## Is OpenHAL a safety system?

No. Firmware still controls each device, so a motor that stops responding on the serial port keeps running. Keep your e-stops, enclosures and hardware interlocks.

## Which AI clients work with OpenHAL?

Any MCP client over stdio, such as Claude Desktop, Claude Code and Cursor. Other clients use JSON-RPC over a WebSocket or stdio, and scripts use the CLI or the Python SDK, all through the same kernel.

## Does the model decide what is safe?

No. The kernel is plain code in the hub, so the same request against the same state always gets the same result.

## Can an agent change a limit?

An agent may tighten a limit for the agent's own session. Loosening a limit, confirming a device file, approving a request and lifting a stop take a person with the human token.

## What happens when a sensor stops responding?

The value turns unknown after a short time, and unknown counts as unsafe, so interlocks and rate limits on the value block commands until a fresh reading arrives. If the device drops off, the hub applies the safe state where the protocol allows.

## Does OpenHAL need firmware on my device?

Not for devices with an existing interface, such as SCPI instruments, Klipper printers or Home Assistant, as [Drivers](/drivers/) lists. On boards you program yourself, the OpenHAL Arduino library adds a self-description and a safe state for when the hub's heartbeat stops.

## Does anything leave my machine?

No. The hub binds to 127.0.0.1, sends no telemetry and connects only to the devices and bridges you configured. Other machines need `api.allow_lan` and a paired token.

## How does OpenHAL relate to MHS?

Anthropic's Model Hardware Standard is a limited research preview for invited labs. OpenHAL is not affiliated with Anthropic or MHS, and the project plans to stay compatible. The [MHS mapping](../../spec/MHS-MAPPING.md) lines device files up with the published MHS.

## Is the browser demo the real kernel?

No. The playground runs a TypeScript port of the kernel's checks that never protects hardware. A test requires the port and the Python kernel to give the same status, code and message.

## What does the device library contain?

One CC0 device file per model, each unverified until tested on a real device. [Add a device](tutorials/add-a-device.md) shows how to contribute.
