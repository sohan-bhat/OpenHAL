# knx driver

The knx driver reads and sets KNX group addresses through a KNXnet/IP interface or router with xknx. Channels come from the ETS group address list, each with a group address and a datapoint type.

## Supports

- Tunneling over UDP or TCP, and routing over multicast.
- DPT 1.x bools, numeric DPTs such as 5.001, 7.x, 9.x, 13.x and 14.x, enum DPTs such as 20.102 with lower case names like `comfort`, and DPT 16 strings.
- DPT units convert to the channel unit.
- `discover()` sends a SEARCH_REQUEST, which only requests interface descriptions.

## Setup

```sh
uv tool install --compile-bytecode "halkit[knx] @ git+https://github.com/sohan-bhat/OpenHAL"
```

KNX Secure isn't supported yet, so enable a plain tunnel for the hub.

| Parameter | Default | Meaning |
|---|---|---|
| `gateway` | required | Interface address for tunneling, or the multicast group for routing. `knx: 192.168.1.20` is shorthand |
| `port` | `3671` | KNXnet/IP port |
| `connection` | `tunneling` | `tunneling`, `tunneling_tcp` or `routing` |
| `local_ip` | automatic | Hub address on the KNX network |
| `individual_address` | from the interface | Hub individual address, needed for routing |
| `route_back` | `false` | Tunneling through NAT |
| `timeout` | `2 s` | Read response deadline |

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
| `group_address` | Address read or sent to, three-level `1/2/3`, two-level `1/2` or free `4660` |
| `dpt` | Quoted datapoint type such as `"9.001"`, since YAML reads an unquoted 5.010 as 5.01 |
| `state_address` | Control channels. Actuator status address for read-back |

## Behavior

- Reads return the newest telegram, or send one GroupValueRead when nothing has arrived. An address with the read flag off reads as no value.
- A command confirms only that the telegram reached the bus, so read the `state_address` to check the actuator.
- Values round to the DPT resolution, such as 51 % for 50.4 %.
- A lost tunnel leaves the device unavailable until the hub reconnects, so nothing goes out late.
- Bad DPTs and malformed addresses fail at load. Values a DPT can't carry are never sent.

## Example

`openhal/drivers/knx/examples/living-room.hal.yaml` switches and dims a ceiling light, sets the heating setpoint and HVAC mode, and keeps the setpoint low while a window is open.

## Limitations

- No KNX Secure, device programming or ETS project import.
- `describe()` returns nothing, since KNX devices can't list their addresses.
- One telegram at a time per file, as the bus carries about 50 a second.

## Hazard default and safe state

Low. `safe_state_support` is `file`. Set each actuator's bus failure behavior in ETS as the real fallback.

## Sources

- xknx documentation, https://xknx.io/
- xknx repository, https://github.com/XKNX/xknx
- KNX Association, KNXnet/IP overview, https://www.knx.org/knx-en/for-professionals/What-is-KNX/A-brief-introduction/
- KNX Association, datapoint types in System Specifications 03.07.02, https://www.knx.org/knx-en/for-professionals/downloads/
