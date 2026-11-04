# Numbers for the stat card

Two numbers for the demo video's stat card. Both were measured or counted on 2026-11-03 from this repository, and the commands below give them again.

| Card | Number | Where it comes from |
|---|---|---|
| Time the hub adds to check a request | 5.5 ms | Median of 1200 requests to the simulated arm, the middle of three runs at 4.9, 5.5 and 5.7 ms |
| Drivers | 34 | The drivers in `openhal/drivers/` that reach hardware, out of 36 in the registry |

## Time the hub adds to check a request

### What the number covers

The clock starts when a request reaches the hub's HTTP app and stops when the driver receives the command. Everything the hub does before the device sees a command falls in between, the HTTP routing, the token lookup, the request model, every safety kernel check, the device lock and the one-time grant the driver checks. The time the request spends on the loopback socket and in the client is outside the number, and the client's own round trip is in the table below for comparison.

### Method

`video/hub/measure_check.py` ran three times, one run after another.

```sh
.venv/bin/python video/hub/measure_check.py --cache video/assets/menagerie --scratch <scratch folder> --count 1200 --out <file>
```

1. Each run starts a real hub from this repository in a fresh home in a scratch folder, with only the simulated SO-101 from `video/hub/so101-demo.hal.yaml` on the mujoco driver, served on a free loopback port. The physics thread runs in the hub's process, as in the recorded take.
2. A thin ASGI wrapper around the hub's app notes the moment each HTTP request arrives. A wrapper around the arm driver's `_write` notes the moment the driver receives a command, after the kernel's checks and the grant check. A wrapper around `Kernel.execute` notes the moment the kernel starts.
3. An agent token with scope `control_medium` sends requests one at a time through `openhal.client.AsyncClient`, the client `openhal mcp` uses. The first 50 requests of each kind warm the hub up and don't count.
4. 1200 writes of `gripper_goal`, alternating between 50 and 50.02 percent so every write passes every check, give the main number.
5. 1200 `move_to` actions at 120 deg/s, which the kernel blocks with LIMIT_EXCEEDED like the take's request, give the time until a blocked request's response starts.

The card uses the median, because the machine was busy with other work and a busy machine adds long tails. The p90 column shows those tails.

### Results

| Run | Added before the driver, median | p10 | p90 | Kernel part, median | Blocked request until its response, median | Client round trip of a write, median |
|---|---|---|---|---|---|---|
| 1 | 5.66 ms | 3.96 ms | 18.71 ms | 1.35 ms | 8.67 ms | 21.94 ms |
| 2 | 5.46 ms | 4.22 ms | 17.64 ms | 1.31 ms | 7.37 ms | 23.17 ms |
| 3 | 4.89 ms | 4.36 ms | 5.85 ms | 1.18 ms | 13.86 ms | 19.03 ms |

The kernel part is the time from `Kernel.execute` to the driver, so about 1.3 ms of the 5.5 ms is the safety kernel and the rest is the HTTP app, the token and the request model. Each run's full result, with p99, minimum and maximum, is in `video/data/stats/check-1.json` to `check-3.json`.

### Conditions

The machine is the 2018 MacBook Pro in `video/README.md`, an Intel Core i7-8750H. During the runs `pmset -g therm` reported a CPU speed limit of 24 to 29 percent of the rated speed, and other agents' builds and renders kept the load average between 9 and 20. On an idle machine the numbers would be lower, so 5.5 ms is a fair upper figure for this laptop, not a best case.

## Drivers

```sh
.venv/bin/python -c "
import json
from pathlib import Path
from openhal.drivers import registry
names = registry.names()
tiers = {name: json.loads((Path('openhal/drivers') / name.replace('-', '_') / 'catalog.json').read_text())['tier'] for name in names}
print(len(names), 'registered,', sum(tier > 0 for tier in tiers.values()), 'reach hardware,', sorted(n for n, t in tiers.items() if t == 0), 'are simulators')
"
```

```
36 registered, 34 reach hardware, ['mock', 'mujoco'] are simulators
```

`registry.names()` lists every package under `openhal/drivers/` that declares a driver `NAME` and `ENTRY`. Each driver's `catalog.json` gives its tier, and tier 0 marks the two drivers that never connect to hardware, `mock` and `mujoco`. The count matches the 34 drivers in the README.
