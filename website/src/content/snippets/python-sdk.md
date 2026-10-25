---
title: Python SDK
---

```sh tested
$ uv run openhal init
$ uv run openhal file confirm ~/.openhal/devices/plant-waterer.hal.yaml
$ uv run openhald
```

```python tested
from openhal.client import connect

with connect() as hub:
    decision = hub.action("plant-waterer", "water", duration={"value": 120, "unit": "s"})
    print(decision.status, decision.code)
```
