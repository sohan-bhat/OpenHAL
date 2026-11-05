# can driver

The can driver reads signals from CAN frames and sends frames as commands and actions, through python-can on SocketCAN or USB adapters such as PCAN, Kvaser, slcan and gs_usb. Classic CAN with 11-bit and 29-bit ids and CAN FD up to 64 bytes both work. The driver is tested on a simulated bus and not yet on a real adapter.

## Setup

```sh
uv tool install --compile-bytecode "halkit[can] @ git+https://github.com/sohan-bhat/OpenHAL"
```

On Linux, run `sudo ip link set can0 up type can bitrate 500000` first. All nodes need the same bitrate and the bus needs 120 ohm termination at both ends. `discover()` lists SocketCAN interfaces that are up, and `describe()` suggests one channel per frame id heard.

| Parameter | Default | Meaning |
|---|---|---|
| `channel` | required | Interface such as `can0`, `PCAN_USBBUS1` or `/dev/ttyACM0`. `can: can0` is shorthand |
| `interface` | `socketcan` | Any python-can interface, such as `pcan`, `kvaser`, `slcan`, `gs_usb` or `virtual` |
| `bitrate` | none | Bit/s for adapters that set the rate. SocketCAN uses `ip link` |
| `fd` | `false` | CAN FD frames |
| `data_bitrate` | none | CAN FD data phase bitrate |
| `timeout` | `1 s` | Send deadline |

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
| `id` | required | Frame id |
| `extended` | `true` above 0x7FF | 29-bit id. Set for low ids on 29-bit buses such as J1939 or VESC |
| `byte`, `length` | `0`, `1` | Start byte and length, 1 to 8 |
| `endian` | `big` | `big` or `little` |
| `signed` | `false` | Two's complement |
| `bit`, `bits` | `0`, the rest | Bit range from the least significant bit |
| `scale`, `offset` | `1`, `0` | device value = raw × scale + offset |
| `unit` | the channel unit | Device unit, converted to the channel unit |
| `on`, `off` | `1`, `0` | Raw bool values |
| `lookup` | none | Raw numbers to enum values, such as `{ 0: coast, 1: eco }` |
| `data` | zeros | Command and action frames. The other bytes |
| `dlc` | the longest field | Command and action frames. Frame length |
| `state` | none | Control channels. Status frame map that shows the result |
| `args` | none | Actions. Field map per argument |

A command starts from the last payload sent with that id, so `enable` keeps the `setpoint` in the same frame. A reconnect starts again from `data`.

## Behavior

- Reads decode the newest frame per id and never transmit. An id not heard since connecting reads as no value.
- Values round to the field's raw step and the reading returned shows the value sent. A value the field can't hold fails with nothing sent.
- A sent frame doesn't prove the node acted, so check a `state` map or a read.
- Frames are never queued or retried. A failed send raises `DriverError` and a hung send `TimeoutError`, with the frame in candump notation.
- An interface that fails to open raises `DriverError` with the `ip link` command to try. Short frames, unmapped raw values and a downed bus raise `DriverError` on read.
- `health()` reports receive errors and bus-off as down.

## Example

`openhal/drivers/can/examples/vesc-motor-controller.hal.yaml` reads a VESC motor controller and sets an ERPM target. The safe state sends zero current so the motor coasts.

## Limitations

- Raw signals only. No CANopen SDO or NMT, J1939 multi-frame transport or ISO-TP, though periodic PDOs and PGNs read fine.
- No DBC import, no remote frames, and fields of at most 8 bytes.

## Hazard default and safe state

Medium. `safe_state_support` is `file`, so safe state frames need the bus and node up. Set the node's own command timeout, which stops most drives when frames stop.

## License note

python-can is LGPL-3.0, used unmodified as an optional dependency with no code copied.

## Sources

- python-can documentation, https://python-can.readthedocs.io/en/stable/
- python-can interfaces, https://python-can.readthedocs.io/en/stable/interfaces.html
- SocketCAN, Linux kernel documentation, https://docs.kernel.org/networking/can.html
- CAN in Automation, CAN FD, https://www.can-cia.org/can-knowledge/can-fd-the-basic-idea
- VESC CAN documentation, https://github.com/vedderb/bldc/blob/master/documentation/comm_can.md
- can-utils with candump and cansend, https://github.com/linux-can/can-utils
