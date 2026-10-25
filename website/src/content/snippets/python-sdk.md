---
title: Python SDK
---

```sh tested
$ uv run openhal init
$ uv run openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml
$ uv run openhald
```

```python tested
from openhal.client import connect

with connect() as hub:
    decision = hub.write("demo-fan", "fan_speed", "150 %")
    print(decision.status, decision.code)
```
