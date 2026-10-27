# upnp driver

The upnp driver reads and controls UPnP devices through their SOAP actions, using async-upnp-client. Media renderers, speakers, TVs and routers publish a description of their services, and each channel is one action, such as `GetVolume` to read and `SetVolume` to change.

## What it supports

- Read channels from any action's output argument, as number, bool, enum or string, with scale, offset and unit.
- Control channels that call an action with `{value}` in one argument, read back through a `state` map.
- Actions that call any SOAP action, with the action's arguments placed by `{name}`.
- A check on connect that every service, action, argument and output exists, and that types and enum values match the device's service descriptions.
- `discover()` sends one SSDP M-SEARCH, which only requests that devices announce themselves.
- `describe()` proposes channels from the Get and Set actions and the actions without outputs.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[upnp] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Find the device's description URL with `discover()` or the device's documentation. Sonos speakers serve the description at `http://<speaker>:1400/xml/device_description.xml`.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `location` | required | The device description URL. The shorthand `upnp: "http://..."` sets it |
| `timeout` | `5 s` | How long one SOAP call may take |

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
| `service` | The service id or type, or the short name in either, such as `RenderingControl` |
| `action` | The SOAP action |
| `args` | Every in-argument of the action, as fixed values or `{value}` and `{name}` places |
| `output` | Reads. The out-argument to read |
| `scale`, `offset`, `unit` | channel value = device value × scale + offset, in `unit` |
| `state` | Control channels. A read map that shows the result |

Arguments are converted to their state variable's type before each call, so `Speed: 1` is sent as the text `1` and a number channel goes out as a whole number when the variable is an integer.

## How reads and commands behave

- Because devices respond to queries quickly and GENA event subscriptions aren't used, a read calls its action every time.
- A control channel without `state` reads as the last value sent, or no value before the first command.
- A SOAP fault becomes `DriverError` with the UPnP error code and description, such as 501 Action Failed or 701 Transition not available.
- `health()` fetches the description again, which is a plain HTTP GET.

## Example

`openhal/drivers/upnp/examples/sonos-speaker.hal.yaml` reads a Sonos speaker's transport state, sets the speaker's volume, up to 40 %, and mute, and plays, pauses and stops the speaker.

## Errors

- A description that can't be fetched or parsed raises `DriverError` naming the location.
- A map whose service, action, arguments or output don't match the device, or whose type or enum values don't, fails the connect with `DriverError` that lists what the device has.
- A device that doesn't respond raises `TimeoutError` or `DriverError` and reports itself disconnected until the device responds again.

## Limitations

- The driver has no GENA eventing, so values are polled.
- The driver doesn't support UPnP Device Protection or HTTPS client certificates.
- The driver has no ContentDirectory browsing helpers, so ContentDirectory actions work like any other action and the DIDL-Lite results come back as text.

## Hazard default and safe state

The default hazard is low, because UPnP devices are mostly media and network equipment. UPnP has no emergency action, so `safe_state_support` is `file`. The hub calls the device file's safe state actions and changes like any others, which needs the device to be reachable.

## Sources

- UPnP Device Architecture 2.0, Open Connectivity Foundation, https://openconnectivity.org/developer/specifications/upnp-resources/upnp/
- UPnP AV RenderingControl and AVTransport service templates, https://openconnectivity.org/developer/specifications/upnp-resources/upnp/
- async-upnp-client, https://github.com/StevenLooman/async_upnp_client
