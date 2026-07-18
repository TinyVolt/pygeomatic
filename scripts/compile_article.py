"""Compile a pygeomatic-in-markdown article to a `{label}(command)` article.

Usage:  uv run python scripts/compile_article.py article.md [-o compiled.md]
        [--ext manifest.json ...] [--macros macros.json ...] [--allow-coercions]
        (or pipe the markdown on stdin with no file argument)

The article's ```pygeomatic fences and inline Python spans run in a subprocess
against one shared store; fences become hidden `{}()` setup spans, group refs
(`{label}(ref:name)`) become hidden-setup-then-visible span runs, and the
compiled document is round-trip validated with `gm.parse_dsl` — a broken
article fails here (exit 1), not on the site. `--ext` / `--macros` (repeatable)
load extension manifests and macro JSON before the article runs;
`--allow-coercions` permits the engine's type-coercions (off by default).

Prints the compiled markdown (or writes it to `-o`) on success.
"""

import argparse
import sys
from pathlib import Path

from pygeomatic import run_article


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="markdown article; stdin if omitted")
    parser.add_argument("-o", "--output", help="write compiled markdown here (default: stdout)")
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

    markdown = Path(args.file).read_text() if args.file else sys.stdin.read()
    result = run_article(
        markdown, extensions=args.ext, macros=args.macros, allow_coercions=args.allow_coercions
    )
    if not result.ok:
        print(result.error, file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(result.markdown)
    else:
        sys.stdout.write(result.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
