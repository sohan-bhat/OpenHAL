# FAQ

## Is OpenHAL a standard?

No. It is an open protocol with a dated specification. Anyone may implement a hub, a client or a driver against it.

## Is OpenHAL a safety system?

No. It checks every command against limits a person set, and it stops everything on request. It can't make firmware obey, and it can't stop a motor that ignores its serial port. Keep your e-stops, enclosures and interlocks wired in hardware.

## Which AI clients work with it?

Any client that speaks MCP over stdio, including Claude Desktop, Claude Code and Cursor. Other clients speak the protocol's JSON-RPC methods over a WebSocket or stdio. Scripts can use the command line or the Python SDK. All of them reach the same kernel.

## Does the model decide what is safe?

No. The kernel is plain code with no model in it, and it runs in the hub, not in the client. The model only sends requests. The same request against the same state always gets the same answer.

## Can an agent change a limit?

It can tighten a limit for its own session. It can't loosen one, confirm a device file, approve its own request or lift a stop. Those need a person with the human token.

## What happens when a sensor stops answering?

Its value becomes unknown after a short time, and unknown never lets a command pass. Interlocks that depend on it block, and rate limits wait for a fresh reading. If the device itself drops off, the hub applies its safe state where the protocol allows it.

## Does it need firmware on my device?

Not for devices that already have an interface, such as bench instruments over SCPI, Klipper printers or Home Assistant entities, once their drivers land. [Drivers](/drivers/) shows which drivers run today. For boards you program yourself, the OpenHAL Arduino library makes the board describe itself and fall to its safe state if the hub goes quiet.

## Does anything leave my machine?

No. The hub binds to 127.0.0.1, sends no telemetry and only talks to the devices and bridges you configured. Other machines need `api.allow_lan` and a paired token.

## How does it relate to MHS?

Anthropic's Model Hardware Standard is a limited research preview for invited labs. OpenHAL is an independent open protocol, not affiliated with Anthropic or MHS. It is open source and usable today with simulators, and it plans to stay compatible. The [MHS mapping](../../spec/MHS-MAPPING.md) shows how device files line up with what has been published so far.

## Is the browser demo the real kernel?

No. The playground runs a TypeScript port of the kernel's checks. A test runs the same commands through both and requires the same status, code and message. The port never protects hardware. The real kernel is the Python one in the hub.

## What does the device library contain?

Device files that people have described and tested, one per model, each with a verification badge. Files there are CC0. See [Add a device](tutorials/add-a-device.md).
