# can driver

The can driver reads signals out of CAN bus frames and sends frames as commands and actions. It uses python-can, so it works with SocketCAN on Linux and with the USB adapters python-can supports (PCAN, Kvaser, slcan, gs_usb and others). Each channel's map says which frame id carries the value and where it sits in the data bytes, so motor drives, battery systems, sensors and homemade nodes work without device-specific code.

## What it supports

- Classic CAN with 11-bit and 29-bit identifiers, and CAN FD with up to 64 data bytes.
- Read channels of type number, bool and enum, decoded from any byte range or bit range, big or little endian, signed or unsigned, with scale, offset and a device unit.
- Control channels that place a value in a frame and send it. Several of them can share one frame.
- Actions that send a fixed frame, with action arguments placed in it.
- `describe()` listens for a moment and proposes one read channel per frame id it sees.
- `discover()` lists SocketCAN interfaces that are up. It sends nothing.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[can] @ git+https://github.com/sohan-bhat/OpenHAL"
```

On Linux, bring the interface up first, for example `sudo ip link set can0 up type can bitrate 500000`. Every node on the bus must use the same bitrate, and the bus needs 120 ohm termination at both ends.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `channel` | required | The interface or channel name, such as `can0`, `PCAN_USBBUS1` or `/dev/ttyACM0`. The shorthand `can: can0` sets it |
| `interface` | `socketcan` | Any python-can interface name, such as `socketcan`, `pcan`, `kvaser`, `slcan`, `gs_usb` or `virtual` |
| `bitrate` | none | Bitrate in bit/s for adapters that set it themselves. SocketCAN takes it from `ip link` instead |
| `fd` | `false` | Use CAN FD frames |
| `data_bitrate` | none | CAN FD data phase bitrate |
| `timeout` | `1 s` | How long a send may take before it fails |

## Channel maps

```yaml
read:
  speed: { unit: rpm, map: { id: 0x101, byte: 0, length: 2 } }
  motor_temp: { unit: degC, map: { id: 0x101, byte: 2, offset: -40 } }
  fault: { type: bool, map: { id: 0x101, byte: 3, bit: 1, bits: 1 } }
write:
  setpoint: { unit: rpm, min: 0, max: 3000, map: { id: 0x201, byte: 0, length: 2, data: [0, 0, 0] } }
  enable:
    type: bool
    map: { id: 0x201, byte: 2, bits: 1, data: [0, 0, 0], state: { id: 0x101, byte: 3, bits: 1 } }
actions:
  clear_fault: { map: { id: 0x2FF, data: [1] } }
```

| Key | Default | Meaning |
|---|---|---|
| `id` | required | The frame identifier |
| `extended` | `true` above 0x7FF | Use a 29-bit identifier. Set it to `true` for low ids on 29-bit buses such as J1939 or VESC |
| `byte`, `length` | `0`, `1` | Where the value starts and how many bytes it spans, 1 to 8 |
| `endian` | `big` | Byte order, `big` or `little` |
| `signed` | `false` | Two's complement |
| `bit`, `bits` | `0`, the rest | The bit range inside those bytes, counted from the least significant bit |
| `scale`, `offset` | `1`, `0` | device value = raw × scale + offset |
| `unit` | the channel unit | The unit the device value is in. It is converted to the channel unit |
| `on`, `off` | `1`, `0` | Raw values for bool channels |
| `lookup` | none | Raw numbers to enum values, such as `{ 0: coast, 1: eco }` |
| `data` | zeros | Command and action frames. The bytes the rest of the frame carries |
| `dlc` | the longest field | Command and action frames. The frame length in bytes |
| `state` | none | Control channels. A read map for the status frame that shows the result |
| `args` | none | Actions. A field map for each action argument |

A change starts from the last payload the driver sent with that id, so changing `enable` keeps the setpoint that `setpoint` put in the same frame. After reconnecting the frame starts from `data` again.

## How reads and commands behave

- CAN only broadcasts. A background thread keeps the newest frame per id, and a read decodes it with the time it arrived. An id that hasn't been seen since connecting reads as no value, which the kernel treats as unknown. Reads never put anything on the bus.
- Values are rounded to the field's raw step, and the reading a command returns shows the value actually sent. A value the field can't hold fails the command and nothing is sent. Nothing is clamped.
- A successful send means the controller put the frame on the bus. It doesn't prove the node acted. Use a `state` map or a read channel to see that.
- Frames are never queued or retried. A failed send fails the command.

## Example

`openhal/drivers/can/examples/vesc-motor-controller.hal.yaml` reads speed, current, temperatures and input voltage from a VESC motor controller and sets an ERPM target. Its safe state sends the zero current frame so the motor coasts.

## Errors

- An interface that can't be opened raises `DriverError` with the `ip link` command to try.
- A frame too short for a field, a raw value a bool or enum map doesn't name, and a bus that went down raise `DriverError` on read.
- A refused send raises `DriverError` and a send that hangs raises `TimeoutError`, each with the frame in candump notation.
- `health()` reports the bus as down after a receive error, and reports bus-off where the interface can tell.

## Limitations

- Raw signals only. CANopen SDO and NMT, J1939 multi-frame transport and ISO-TP are not handled, so values that need a request and reply protocol can't be read. Their periodic PDOs and PGNs can.
- No DBC file import. Make the maps from the node's documentation or DBC file by hand.
- No remote frames.
- Fields are at most 8 bytes long.

## Hazard default and safe state

The default hazard is medium, because CAN nodes are usually motor drives, battery systems and actuators. CAN has no emergency behavior of its own, so `safe_state_support` is `file`. The hub sends the device file's safe state frames like any other frame, which needs the bus and the node to be up. Most drives stop on their own when command frames stop arriving. Configure that timeout on the node, because it is the real fallback when the hub or the bus fails.

## License note

python-can is licensed LGPL-3.0. OpenHAL uses it unmodified as an optional dependency and copies none of its code.

## Sources

- python-can documentation, https://python-can.readthedocs.io/en/stable/
- python-can interfaces, https://python-can.readthedocs.io/en/stable/interfaces.html
- SocketCAN, Linux kernel documentation, https://docs.kernel.org/networking/can.html
- CAN in Automation, CAN FD, https://www.can-cia.org/can-knowledge/can-fd-the-basic-idea
- VESC CAN documentation, https://github.com/vedderb/bldc/blob/master/documentation/comm_can.md
- can-utils (candump, cansend), https://github.com/linux-can/can-utils
