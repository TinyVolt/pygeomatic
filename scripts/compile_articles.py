"""Compile every pygeomatic-in-markdown article under a directory.

Usage:  uv run python scripts/compile_articles.py SRC_DIR OUT_DIR
        [--ext manifest.json ...] [--macros macros.json ...] [--allow-coercions]

Every `*.md` under SRC_DIR (recursively) is compiled with the same pipeline as
scripts/compile_article.py and written to the same relative path under
OUT_DIR; every other regular file (images, ...) is copied through verbatim so
OUT_DIR is a publishable tree. Hidden files and directories are skipped.

All articles are attempted before failing: each error is reported to stderr
with its file and article line, and the exit code is 1 if ANY article failed —
this is the CI gate behind the `TinyVolt/pygeomatic` GitHub Action.
"""

import argparse
import shutil
import sys
from pathlib import Path

from pygeomatic import run_article


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="directory containing the markdown articles")
    parser.add_argument("output", help="directory to write the compiled tree to")
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

    src = Path(args.source)
    out = Path(args.output)
    if not src.is_dir():
        print(f"source directory not found: {src}", file=sys.stderr)
        return 1

    files = [
        p
        for p in sorted(src.rglob("*"))
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(src).parts)
    ]
    articles = [p for p in files if p.suffix == ".md"]

    failures = 0
    for path in files:
        rel = path.relative_to(src)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix != ".md":
            shutil.copy2(path, dst)
            continue
        result = run_article(
            path.read_text(),
            extensions=args.ext,
            macros=args.macros,
            allow_coercions=args.allow_coercions,
        )
        if result.ok:
            dst.write_text(result.markdown)
            print(f"compiled {rel}")
        else:
            failures += 1
            print(f"FAILED {rel}\n{result.error}\n", file=sys.stderr)

    print(f"{len(articles) - failures}/{len(articles)} article(s) compiled")
    if failures:
        print(f"{failures} article(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
