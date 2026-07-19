# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_emit.py

# Run a single test by name
uv run pytest tests/test_emit.py::test_function_name

# Run a build file through the DSL pipeline
uv run python scripts/build_to_dsl.py build.py
uv run python scripts/build_to_dsl.py build.py --ext dist/manifest.json --macros my-macros.json

# Regenerate registry.json and coercions.json from the TypeScript source
npm run gen:registry
```

## Architecture

pygeomatic is a **Python mirror of a TypeScript DSL** ("geomatic"). Every public function maps 1:1 to a DSL command: calling it both computes numeric values (numpy) **and** records the call onto an append-only tape, from which `emit()` produces deterministic DSL lines.

### Core data flow

```
Python call → registry.py (geomatic_fn decorator) → store.py (tape + nodes) → emit.py (DSL text)
                                                           ↑
                                               parse.py (inverse: DSL → tape)
```

**`nodes.py`** — All geomatic node types (`GNode` subclasses: `Point`, `Scalar`, `Circle`, `Array`, etc.). Nodes hold optional numeric payloads in private `PrivateAttr` fields. Property access (`.x`, `.center`, etc.) returns a new node carrying a `PropRef` that serializes to the `base.field` DSL argument form. Infix arithmetic is deliberately rejected — use `gm.add(a, b)` etc.

**`store.py`** — The `Store` holds two things: `commands: list[Command]` (the tape) and `nodes: dict[str, GNode]` (id → node map). A `Store` is a context manager; without one the module-level default store is used. `NameGenerator` mirrors the TypeScript `NameGenerator.ts` but uses dashed ids (`num-0`, `p-1`) to prevent collisions with engine-generated undashed ids (`num0`, `p1`). Two `ContextVar`s control replay modes: `_allow_engine_ids` (set during `parse_dsl`) and `_macro_replay` (set during macro body execution).

**`registry.py`** — The `@geomatic_fn` decorator registers a Python function as a geomatic command. It handles argument binding (`_bind`), type validation (`_node_accepts`), implicit `\text`/`\bool` coercions for bare Python `str`/`bool` arguments, and tape recording. `REGISTRY: dict[str, FunctionDef]` maps DSL keywords to their `FunctionDef`. A `str` filling a non-Text parameter names a node by id: the existing node, or — for Point/Scalar (and, from parse replay, Text) parameters — an auto-created one with a random payload, mirroring the engine's `CommandExecutor.createAndSaveNode`. Auto-created nodes are store-only (no tape command; the engine re-creates them on replay); the article round-trip gate disables auto-create (`store._auto_create_enabled`) to keep catching define-before-use violations.

**`emit.py`** — Renders the tape as newline-joined DSL. Numbers use positional notation only (no scientific notation).

**`parse.py`** — Inverse of `emit`: replays DSL lines through the registered Python functions onto the active store. Engine-auto-id shape (`p0`, `num1`) is accepted during parse even though it's rejected for authored `out=` ids.

**`coercions.py`** + `coercions.json` — Type-coercion table generated from TypeScript (`canCoerce`/`canCoerceValue`). Coercions are **off by default**; enable with `gm.allow_coercions(True)` or the `--allow-coercions` flag. Controlled via `_coercions_enabled` ContextVar.

**`functions/`** — All DSL command implementations. Organized into:
- `implementations/` — numeric computations grouped by domain (`planar_geometry.py`, `curve_functions.py`, `scalar_functions.py`, etc.)
- `overloads/` — operator overloads (`add.py`, `mul.py`, etc.) registered via `create_overload.py`

**`extensions.py`** — Dynamic registration of geomatic extension manifests (`manifest.json`). Extensions are pure graph-record (compute is never run in Python); outputs are record-only nodes with `.numeric = None`. The `_LOADED` and `_KEYWORD_SOURCE` dicts track provenance for unload/replace.

**`macros.py`** — Macro support (bundles of DSL commands). The builtin set from `macros.json` is registered on import. Macro invocations record ONE line on the tape while replaying the body locally using `_macro_replay` mode (engine semantics: undashed auto-ids, last-write-wins on reassignment).

**`generate.py`** + **`runner.py`** + **`prompting.py`** — LLM code-generation pipeline. `generate_dsl(prompt, complete)` drives an LLM retry loop. The adapter (`complete`) is injected by the caller — pygeomatic never imports an LLM SDK. `runner.py` executes `build(gm)` code in a subprocess and returns `.dsl` or `.error`. `prompting.py` renders `system_prompt()` from the live REGISTRY (so it automatically includes loaded extensions and macros).

### Parity with TypeScript

`registry.json` and `src/pygeomatic/coercions.json` are **generated** from the live TypeScript source via `npm run gen:registry`. After changing TypeScript functions, regenerate and run `tests/test_parity.py` to verify the Python registry matches exactly.

### Key constraints

- **No infix arithmetic on nodes**: `a + b` raises. Each Python call = exactly one DSL line.
- **Id grammar**: letters, digits, dashes only; no underscores. Engine auto-ids (`p0`, `num1`) are rejected for authored `out=` — use dashed forms (`p-0`, `num-1`) or descriptive names.
- **Text is single-line**: newlines in text values are collapsed to a single space.
- **Coercions off by default**: pass exact node types unless you've explicitly enabled coercions.
