# Create a routine

A routine is an automation that runs on the [Hub](glossary:hub) without a model. Triggers say when it runs. Steps say what it does. Every change a step makes goes through the [Safety Kernel](glossary:safety-kernel), like any other command.

## Start the hub

```sh tested
$ uv run openhal init
$ uv run openhal file confirm ~/.openhal/devices/plant-waterer.hal.yaml
$ uv run openhald &
$ uv run openhal read plant-waterer.soil_moisture
```

## Describe it

This routine checks the soil every hour and waters the plant for 20 seconds when it is dry.

```yaml tested kind=routine file=morning-water.yaml
id: morning-water
triggers:
  - every: 1 h
steps:
  - if: "plant-waterer.soil_moisture < 35 %"
    then:
      - action: { device: plant-waterer, action: water, args: { duration: 20 s } }
```

## Store it and dry run it

A new routine starts disabled. A dry run checks every command in every branch against the current state, and nothing reaches the device.

```sh tested
$ uv run openhal routine new morning-water --file morning-water.yaml
stored morning-water, disabled.
$ uv run openhal routine dry-run morning-water
dry run passes
  1. allowed  Allowed.
```

## Enable it

Only a person may enable a routine, by typing the phrase `enable`. The hub runs the dry run again first.

```sh tested
$ uv run openhal routine enable morning-water
enabled  morning-water
```

## A routine the kernel refuses

A step outside the limits fails the dry run, so the routine can't be enabled.

```yaml tested kind=routine file=long-soak.yaml
id: long-soak
triggers:
  - every: 1 h
steps:
  - action: { device: plant-waterer, action: water, args: { duration: 120 s } }
```

```sh tested
$ uv run openhal routine new long-soak --file long-soak.yaml
$ uv run openhal routine dry-run long-soak
blocked above_max  Blocked. The duration limit is 30 s (max). Asked for 120 s.
```

The file also caps the pump at 3 runs per hour, and a routine's runs count toward it. Over the protocol, `hal/routines/dryRun` returns the same decisions. The [routines section](../../../spec/2026-10-24/routines.md) of the specification defines triggers, steps and approvals for high hazard devices.
