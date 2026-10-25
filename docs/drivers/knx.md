# knx driver

The knx driver reads and sets KNX group addresses through a KNXnet/IP interface or router, using xknx. Each channel names a group address and its datapoint type (DPT), so lights, dimmers, blinds, thermostats and sensors from any KNX manufacturer work from a group address list, such as the one ETS exports.

## What it supports

- KNXnet/IP tunneling over UDP or TCP, and KNXnet/IP routing over multicast.
- Read channels of type bool (DPT 1.x), number (numeric DPTs such as 5.001, 7.x, 9.x, 13.x and 14.x), enum (enum DPTs such as 20.102) and string (DPT 16).
- Channels under `write` that send a GroupValueWrite, read back from the actuator's status address.
- Units from the DPT, converted to the channel unit, such as DPT 9.001 in degC to a channel in degF.
- `discover()` sends a KNXnet/IP SEARCH_REQUEST, which only asks interfaces to describe themselves.

## Setup

```sh
uv pip install 'openhal-hub[knx]'
```

You need a KNXnet/IP interface or router on the network, and the group address list from the ETS project with each address's DPT.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `gateway` | required | The interface's address for tunneling, or the multicast group for routing. The shorthand `knx: 192.168.1.20` sets it |
| `port` | `3671` | KNXnet/IP port |
| `connection` | `tunneling` | `tunneling`, `tunneling_tcp` or `routing` |
| `local_ip` | found automatically | The hub's address on the KNX network |
| `individual_address` | from the interface | The hub's own individual address, needed for routing |
| `route_back` | `false` | For tunneling through NAT |
| `timeout` | `2 s` | How long a read waits for an answer |

KNX Secure isn't supported yet, so a secure interface needs a plain tunnel enabled for the hub.

## Channel maps

```yaml
read:
  temperature: { unit: degC, map: { group_address: 3/1/0, dpt: "9.001" } }
write:
  ceiling_light: { type: bool, map: { group_address: 1/1/0, dpt: "1.001", state_address: 1/1/1 } }
  ceiling_dimmer: { unit: percent, min: 0, max: 100, map: { group_address: 1/1/2, dpt: "5.001", state_address: 1/1/3 } }
```

| Key | Meaning |
|---|---|
| `group_address` | The address the channel reads, or sends to. Three-level (`1/2/3`), two-level (`1/2`) or free (`4660`) |
| `dpt` | The datapoint type, quoted, such as `"9.001"`. YAML reads an unquoted 5.010 as the number 5.01 |
| `state_address` | For channels under `write`, the actuator's status address to read back |

Enum channels use the DPT's names in lower case, such as `comfort` and `economy` for DPT 20.102.

## How reads and commands behave

- The driver listens to every telegram for its addresses. A read returns the newest value with the time it arrived. When nothing has arrived since connecting, the read sends one GroupValueRead and waits `timeout`. An address whose read flag is off never answers, and reads as no value until a telegram arrives.
- A command waits for the interface's L_Data.con, which proves the telegram reached the bus, not that an actuator acted. The status address shows that.
- Values are rounded to the DPT's resolution. A channel without a status address reads back the value as encoded, such as 51 % for 50.4 %.
- xknx's own reconnect is off. A lost tunnel leaves the device unavailable until the hub reconnects, so nothing goes out late.

## Example

`openhal/drivers/knx/examples/living-room.hal.yaml` switches and dims a ceiling light, sets the heating setpoint and the HVAC mode, and keeps the setpoint low while a window is open.

## Errors

- An interface that refuses the tunnel or can't be reached raises `DriverError` or `TimeoutError`.
- A channel whose DPT doesn't fit its type or unit, an unknown DPT and a malformed group address fail when the device file loads, with `DriverError`.
- A command the interface doesn't confirm raises `DriverError` or `TimeoutError` naming the group address. A value the DPT can't carry raises `DriverError` and nothing is sent.

## Limitations

- No KNX Secure, no device management (programming, individual address changes) and no ETS project import.
- `describe()` returns nothing, because KNX devices can't list their group addresses.
- One telegram at a time per device file, as the KNX bus is slow (about 50 telegrams a second).

## Hazard default and safe state

The default hazard is low, because most KNX group addresses switch lights and blinds and set room temperatures. KNX has no emergency command of its own, so `safe_state_support` is `file`. The hub sends the device file's safe state like any other telegram, which needs the interface and the bus to be up. Actuators have their own behavior on bus voltage failure and recovery, set in ETS, which is the real fallback.

## Sources

- xknx documentation, https://xknx.io/
- xknx repository, https://github.com/XKNX/xknx
- KNX Association, KNXnet/IP overview, https://www.knx.org/knx-en/for-professionals/What-is-KNX/A-brief-introduction/
- KNX Association, datapoint types (System Specifications 03.07.02), https://www.knx.org/knx-en/for-professionals/downloads/
