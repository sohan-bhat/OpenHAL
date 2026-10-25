"""Load the sila2 package under whichever protobuf implementation the process already uses.

sila2 0.14 sets PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION to python when it is imported, then loads
both its pregenerated `sila2.framework.pb2.SiLAFramework_pb2` and a copy it compiles at run time.
Both register `SiLAFramework.proto`. Protobuf's pure Python pool accepts that. upb, protobuf's
default, refuses the second file because the two builds differ. When another package, such as
aioesphomeapi, imported protobuf first, upb is fixed for the whole process and `import sila2`
fails with "duplicate file name SiLAFramework.proto".

`ensure()` compiles the framework protos once with grpc_tools and registers that one build under
both module names before sila2 loads, so every later registration is identical and upb accepts
it. When protobuf isn't loaded yet, sila2 picks the pure Python implementation itself and nothing
needs doing.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import tempfile
import threading
from pathlib import Path
from typing import Final

FRAMEWORK: Final = ("SiLAFramework", "SiLABinaryTransfer")
_LOCK = threading.Lock()


def ensure() -> None:
    """Make `import sila2.framework` safe. Idempotent and cheap after the first call."""
    with _LOCK:
        if "sila2.framework" in sys.modules or "google.protobuf" not in sys.modules:
            return
        from google.protobuf.internal import api_implementation  # type: ignore[import-untyped]

        if api_implementation.Type() == "python":
            return
        _register_one_build()


def _register_one_build() -> None:
    from grpc_tools import protoc  # type: ignore[import-untyped]

    spec = importlib.util.find_spec("sila2")
    if spec is None or spec.origin is None:
        return
    resources = Path(spec.origin).parent / "resources" / "proto"
    with tempfile.TemporaryDirectory() as folder:
        for name in FRAMEWORK:
            arguments = [
                "protoc",
                f"--proto_path={resources}",
                f"--python_out={folder}",
                f"--grpc_python_out={folder}",
                str(resources / f"{name}.proto"),
            ]
            if protoc.main(arguments) != 0:
                raise RuntimeError(f"grpc_tools could not compile {name}.proto")
        sys.path.insert(0, folder)
        try:
            for name in FRAMEWORK:
                for suffix in ("_pb2", "_pb2_grpc"):
                    module = importlib.import_module(f"{name}{suffix}")
                    sys.modules[f"sila2.framework.pb2.{name}{suffix}"] = module
        finally:
            sys.path.remove(folder)
