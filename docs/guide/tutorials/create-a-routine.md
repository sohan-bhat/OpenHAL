# Create a routine

A routine is an automation that runs on the [Hub](glossary:hub) without a model. Triggers say when it runs. Steps say what it does. Every change a step makes goes through the [Safety Kernel](glossary:safety-kernel), like any other command.

## Start the hub

```sh tested
$ uv run openhal init
$ uv run openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml
$ uv run openhald &
```

## Describe it

This routine checks the fan's temperature every 30 seconds and picks a speed.

```yaml tested kind=routine file=keep-cool.yaml
id: keep-cool
triggers:
  - every: 30 s
steps:
  - if: "demo-fan.temperature > 28 degC"
    then:
      - write: { device: demo-fan, channel: fan_speed, value: 60 % }
    else:
      - write: { device: demo-fan, channel: fan_speed, value: 20 % }
```

## Store it and dry run it

A new routine starts disabled. A dry run checks every change in every branch against the current state, and nothing reaches the device.

```sh tested
$ uv run openhal routine new keep-cool --file keep-cool.yaml
stored keep-cool, disabled.
$ uv run openhal routine dry-run keep-cool
dry run passes
  1. allowed  Allowed.
  2. allowed  Allowed.
```

## Enable it

Only a person may enable a routine, by typing the phrase `enable`. The hub runs the dry run again first.

```sh tested
$ uv run openhal routine enable keep-cool
enabled  keep-cool
```

## A routine the kernel refuses

A step outside the limits fails the dry run, so the routine can't be enabled.

```yaml tested kind=routine file=full-blast.yaml
id: full-blast
triggers:
  - every: 30 s
steps:
  - write: { device: demo-fan, channel: fan_speed, value: 150 % }
```

```sh tested
$ uv run openhal routine new full-blast --file full-blast.yaml
$ uv run openhal routine dry-run full-blast
blocked above_max  Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.
```

If a limit tightens after a routine is enabled, its next run is blocked the same way. Over the protocol, `hal/routines/dryRun` returns the same decisions. The [routines section](../../../spec/2026-10-24/routines.md) of the specification defines triggers, steps and approvals for high hazard devices.
