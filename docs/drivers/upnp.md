# upnp driver

The upnp driver reads and controls UPnP devices through their SOAP actions with async-upnp-client. Media renderers, speakers, TVs and routers publish service descriptions, and each channel is one action, such as `GetVolume` to read and `SetVolume` to change.

## Supports

- Reads from any action's output argument as number, bool, enum or string, with scale, offset and unit.
- Control channels that call an action with `{value}` in one argument, read back through a `state` map or else the last value sent.
- Actions that call any SOAP action, with arguments placed by `{name}`.
- A connect check that every service, action, argument and output exists with matching types and enum values.
- `discover()` sends one SSDP M-SEARCH. `describe()` suggests channels from the Get and Set actions and the actions without outputs.

## Setup

```sh
uv tool install --compile-bytecode "halkit[upnp] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Find the description URL with `discover()` or the device documentation. Sonos speakers serve `http://<speaker>:1400/xml/device_description.xml`.

| Parameter | Default | Meaning |
|---|---|---|
| `location` | required | Device description URL. `upnp: "http://..."` is shorthand |
| `timeout` | `5 s` | Per SOAP call |

## Channel maps

```yaml
read:
  transport_state:
    type: enum
    values: [STOPPED, PLAYING, PAUSED_PLAYBACK, TRANSITIONING, NO_MEDIA_PRESENT]
    map: { service: AVTransport, action: GetTransportInfo, args: { InstanceID: 0 }, output: CurrentTransportState }
write:
  volume:
    unit: percent
    min: 0
    max: 40
    map:
      service: RenderingControl
      action: SetVolume
      args: { InstanceID: 0, Channel: Master, DesiredVolume: "{value}" }
      state: { service: RenderingControl, action: GetVolume, args: { InstanceID: 0, Channel: Master }, output: CurrentVolume }
actions:
  play: { map: { service: AVTransport, action: Play, args: { InstanceID: 0, Speed: "1" } } }
```

| Key | Meaning |
|---|---|
| `service` | Service id or type, or the short name in either, such as `RenderingControl` |
| `action` | SOAP action |
| `args` | Every in-argument, as fixed values or `{value}` and `{name}` places |
| `output` | Reads. The out-argument to read |
| `scale`, `offset`, `unit` | value = device value × scale + offset, in `unit` |
| `state` | Control channels. Read map that shows the result |

Arguments convert to the state variable's type before each call, so `Speed: 1` goes out as the text `1` and numbers go out whole for integer variables.

## Behavior

- Every read calls the action, since GENA events aren't used.
- A SOAP fault becomes `DriverError` with the UPnP code and description, such as 501 Action Failed or 701 Transition not available.
- `health()` fetches the description again with a plain HTTP GET.
- A description that fails to fetch or parse raises `DriverError` naming the location. A map that doesn't match the device fails the connect, listing what the device has. A silent device raises `TimeoutError` or `DriverError` and reads as disconnected until the device responds.

## Example

`openhal/drivers/upnp/examples/sonos-speaker.hal.yaml` reads a Sonos speaker's transport state, sets volume up to 40 % and mute, and plays, pauses and stops.

## Limitations

- No GENA eventing, so values are polled.
- No UPnP Device Protection or HTTPS client certificates.
- No ContentDirectory helpers. ContentDirectory actions work like any other, with DIDL-Lite results as text.

## Hazard default and safe state

Low. `safe_state_support` is `file`, called while the device is reachable.

## Sources

- UPnP Device Architecture 2.0, Open Connectivity Foundation, https://openconnectivity.org/developer/specifications/upnp-resources/upnp/
- UPnP AV RenderingControl and AVTransport service templates, https://openconnectivity.org/developer/specifications/upnp-resources/upnp/
- async-upnp-client, https://github.com/StevenLooman/async_upnp_client
