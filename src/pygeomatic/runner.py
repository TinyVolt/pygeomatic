"""Execute generated `build(gm)` code in a subprocess and collect the DSL.

The subprocess uses the same interpreter as the caller (so pygeomatic is
importable), gets the code on stdin, and prints the emitted DSL on stdout.
Failures (syntax errors, bad calls, missing `build`, timeouts) come back as
text suitable for feeding straight back to a model.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional, Sequence

_DRIVER = """\
import linecache
import sys

code = sys.stdin.read()
# Seed linecache so assignment-target name inference (inference.py) can see
# the source of the exec'd code.
linecache.cache["<generated>"] = (len(code), None, code.splitlines(True), "<generated>")
namespace = {}
exec(compile(code, "<generated>", "exec"), namespace)

build = namespace.get("build")
if not callable(build):
    raise SystemExit("generated code must define a function `build(gm)`")

import pygeomatic as gm

argv = sys.argv[1:]
allow_coercions = "--allow-coercions" in argv
macros = [a[len("--macros="):] for a in argv if a.startswith("--macros=")]
extensions = [
    a for a in argv if a != "--allow-coercions" and not a.startswith("--macros=")
]

for _src in extensions:
    gm.load_extensions(_src)
for _src in macros:
    gm.load_macros(_src)

with gm.Store() as store:
    if allow_coercions:
        with gm.allow_coercions():
            build(gm)
    else:
        build(gm)

sys.stdout.write(gm.emit(store))
"""


@dataclass
class RunResult:
    ok: bool
    dsl: list[str] = field(default_factory=list)
    error: Optional[str] = None
    code: str = ""


def run_generated(
    code: str,
    timeout: float = 20.0,
    extensions: Sequence[str] = (),
    macros: Sequence[str] = (),
    allow_coercions: bool = False,
) -> RunResult:
    """Run generated code (must define `build(gm)`) and return the DSL lines.

    `extensions` are manifest.json sources (paths/URLs) loaded via
    `gm.load_extensions` in the subprocess before `build` runs; `macros` are
    macro JSON sources loaded via `gm.load_macros` (the builtin geometry.json
    macros are always available). `allow_coercions` permits the engine's
    type-coercions (off by default → strict exact types).
    """
    driver_args = [*extensions, *(f"--macros={src}" for src in macros)]
    if allow_coercions:
        driver_args.append("--allow-coercions")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DRIVER, *driver_args],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            ok=False,
            error=f"execution timed out after {timeout}s (infinite loop?)",
            code=code,
        )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or f"exited with code {proc.returncode}"
        # Keep the tail — the exception is at the end of a traceback.
        lines = err.splitlines()
        if len(lines) > 30:
            err = "\n".join(lines[-30:])
        return RunResult(ok=False, error=err, code=code)
    dsl = [line for line in proc.stdout.splitlines() if line.strip()]
    return RunResult(ok=True, dsl=dsl, code=code)
