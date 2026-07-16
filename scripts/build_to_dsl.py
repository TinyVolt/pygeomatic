"""Run a file containing `def build(gm): ...` and print the emitted DSL.

Usage:  uv run python scripts/build_to_dsl.py <file.py> [--ext manifest.json ...]
        [--macros macros.json ...] [--allow-coercions]
        (or pipe the code on stdin with no file argument)

`--ext` (repeatable) loads extension manifests via `gm.load_extensions` before
`build` runs, so extension commands can be recorded. `--macros` (repeatable)
loads additional macro JSON files via `gm.load_macros` (the builtin
geometry.json macros are always available). `--allow-coercions` permits
the engine's type-coercions (off by default → strict exact types).

Prints the DSL commands on success (exit 0); prints the error on failure
(exit 1). This is the executor behind the /geomatic-dsl chat skill.
"""

import argparse
import sys
from pathlib import Path

from pygeomatic import run_generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="python file defining build(gm); stdin if omitted")
    parser.add_argument(
        "--ext",
        action="append",
        default=[],
        metavar="MANIFEST",
        help="extension manifest.json (path or URL); repeatable",
    )
    parser.add_argument(
        "--macros",
        action="append",
        default=[],
        metavar="MACROS_JSON",
        help="macro JSON file (path or URL, downloadMacro format); repeatable. "
        "The builtin geometry.json macros are always loaded.",
    )
    parser.add_argument(
        "--allow-coercions",
        action="store_true",
        help="permit engine type-coercions (default off → strict exact types)",
    )
    args = parser.parse_args()

    code = Path(args.file).read_text() if args.file else sys.stdin.read()
    result = run_generated(
        code, extensions=args.ext, macros=args.macros, allow_coercions=args.allow_coercions
    )
    if result.ok:
        print("\n".join(result.dsl))
        return 0
    print(result.error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
