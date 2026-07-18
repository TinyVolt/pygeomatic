#!/usr/bin/env bash
#
# Sync files that changed in a source repo into this repo.
#
# The source repo keeps the package under a `python/` subtree, which maps 1:1
# onto the root of this repo (python/src/... -> src/..., python/tests/... -> tests/...).
#
# The set of files is derived from `git status` in the source repo, so any file
# modified, created, or deleted under the subtree is synced automatically:
#   - modified / created / untracked -> copied here (via rsync)
#   - deleted                        -> deleted here
#   - renamed                        -> new path copied, old path deleted
#
# Usage:
#   scripts/copy_from_tinyvolt.sh <source-repo>             # sync the files
#   scripts/copy_from_tinyvolt.sh --dry-run <source-repo>   # show what would happen
#
# Options:
#   -n, --dry-run          show what would change, write nothing
#   --subtree <dir>        subtree in the source repo to sync (default: python)
#
set -euo pipefail

SRC_SUBTREE="python"   # subtree in the source repo that mirrors this repo's root
DEST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { echo "usage: $(basename "$0") [--dry-run|-n] [--subtree <dir>] <source-repo>" >&2; }

DRY_RUN=0
SRC_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|-n) DRY_RUN=1; shift ;;
    --subtree) SRC_SUBTREE="${2:?--subtree needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option: $1" >&2; usage; exit 2 ;;
    *)
      if [[ -n "$SRC_ROOT" ]]; then
        echo "error: unexpected argument: $1" >&2; usage; exit 2
      fi
      SRC_ROOT="$1"; shift ;;
  esac
done

if [[ -z "$SRC_ROOT" ]]; then
  echo "error: missing <source-repo> argument" >&2
  usage
  exit 2
fi
SRC_ROOT="${SRC_ROOT%/}"

if [[ ! -d "$SRC_ROOT/.git" && ! -f "$SRC_ROOT/.git" ]]; then
  echo "error: source is not a git repo: $SRC_ROOT" >&2
  exit 1
fi

if [[ ! -d "$SRC_ROOT/$SRC_SUBTREE" ]]; then
  echo "error: subtree not found: $SRC_ROOT/$SRC_SUBTREE" >&2
  exit 1
fi

# Collect changed paths from git, split into copies vs deletes.
# Paths are relative to the subtree (the `python/` prefix is stripped).
copies=()
deletes=()

strip_prefix() { printf '%s' "${1#"$SRC_SUBTREE"/}"; }

while IFS= read -r -d '' entry; do
  status="${entry:0:2}"
  path="${entry:3}"
  index="${status:0:1}"
  case "$index" in
    R|C)
      # Rename/copy: the old path follows as a second NUL-terminated field.
      IFS= read -r -d '' oldpath || true
      [[ "$index" == "R" ]] && deletes+=( "$(strip_prefix "$oldpath")" )
      copies+=( "$(strip_prefix "$path")" )
      ;;
    *)
      if [[ "$status" == *D* ]]; then
        deletes+=( "$(strip_prefix "$path")" )
      else
        copies+=( "$(strip_prefix "$path")" )
      fi
      ;;
  esac
done < <(git -C "$SRC_ROOT" status --porcelain -z -- "$SRC_SUBTREE/")

if [[ ${#copies[@]} -eq 0 && ${#deletes[@]} -eq 0 ]]; then
  echo "nothing changed under $SRC_SUBTREE/ in $SRC_ROOT — nothing to do."
  exit 0
fi

# Copies: one rsync call, structure preserved relative to the subtree.
if [[ ${#copies[@]} -gt 0 ]]; then
  echo "== copying ${#copies[@]} file(s) =="
  rsync_flags=(-av --from0 --files-from=-)
  [[ $DRY_RUN -eq 1 ]] && rsync_flags+=(--dry-run)
  printf '%s\0' "${copies[@]}" \
    | rsync "${rsync_flags[@]}" "$SRC_ROOT/$SRC_SUBTREE/" "$DEST_ROOT/"
fi

# Deletes: rsync's delete flags aren't available in openrsync, so remove directly.
if [[ ${#deletes[@]} -gt 0 ]]; then
  echo "== deleting ${#deletes[@]} file(s) =="
  for rel in "${deletes[@]}"; do
    target="$DEST_ROOT/$rel"
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "would delete: $rel"
    elif [[ -e "$target" ]]; then
      rm -f "$target"
      echo "deleted: $rel"
    else
      echo "already absent: $rel"
    fi
  done
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "dry run only — nothing was written. Re-run without --dry-run to apply."
fi
