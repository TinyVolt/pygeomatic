"""Assignment-target output-id inference (inference.py).

`p = gm.point(3, 4)` must behave like `p = gm.point(3, 4, out="p")`; anything
ambiguous or unsafe must silently fall back to the auto-generated id.
"""

import pytest

import pygeomatic as gm


def test_simple_assignment_infers_id():
    with gm.Store() as s:
        p = gm.point(3, 4)
    assert p.id == "p"
    assert gm.emit(s) == "p = \\point 3 4"


def test_underscores_become_dashes():
    with gm.Store():
        fwd_traj = gm.point(1, 2)
    assert fwd_traj.id == "fwd-traj"


def test_explicit_out_wins_over_assignment_target():
    with gm.Store():
        p = gm.point(3, 4, out="start")
    assert p.id == "start"


def test_no_assignment_gets_auto_id():
    with gm.Store() as s:
        gm.point(3, 4)
    assert gm.emit(s) == "p-0 = \\point 3 4"


def test_nested_call_only_names_the_outer_call():
    with gm.Store() as s:
        q = gm.mid_point(gm.point(0, 0), gm.point(2, 2))
    assert q.id == "q"
    assert gm.emit(s) == "\n".join(
        [
            "p-0 = \\point 0 0",
            "p-1 = \\point 2 2",
            "q = \\mid-point p-0 p-1",
        ]
    )


def test_multiline_call_is_inferred():
    with gm.Store():
        anchor = gm.point(
            5,
            6,
        )
    assert anchor.id == "anchor"


def test_walrus_assignment_is_inferred():
    with gm.Store():
        nodes = [(w := gm.point(1, 1)), gm.point(2, 2)]
    assert nodes[0] is w
    assert w.id == "w"
    assert nodes[1].id == "p-0"


def test_annotated_assignment_is_inferred():
    with gm.Store():
        origin: object = gm.point(0, 0)
    assert origin.id == "origin"


def test_loop_reuse_falls_back_to_auto_after_first():
    with gm.Store() as s:
        for i in range(3):
            p = gm.point(i, 0)
    assert p.id == "p-1"  # third iteration; first claimed "p"
    lines = gm.emit(s).splitlines()
    assert lines == ["p = \\point 0 0", "p-0 = \\point 1 0", "p-1 = \\point 2 0"]


def test_engine_auto_shaped_name_falls_back():
    # p1/num3/... are the engine's internal auto-name space; inferring them
    # would recreate the silent-clobber footgun that explicit out= rejects.
    with gm.Store():
        p1 = gm.point(3, 4)
    assert p1.id == "p-0"


def test_system_default_name_falls_back():
    # T is a seeded system node; an inferred name never reassigns it.
    with gm.Store():
        T = gm.scalar(2)
    assert T.id == "num-0"


def test_invalid_python_names_fall_back():
    with gm.Store():
        _hidden = gm.point(1, 1)  # leading underscore → "-hidden" is invalid
    assert _hidden.id == "p-0"


def test_multi_target_assignment_infers_both_scopes():
    # function scope (CALL→STORE→STORE, no SWAP)
    with gm.Store():
        a, b = gm.point(1, 1), gm.point(2, 2)
    assert a.id == "a"
    assert b.id == "b"
    # module scope compiles differently (CALL→SWAP→STORE→STORE)
    ns = {"gm": gm}
    with gm.Store():
        exec(compile("a, b = gm.point(1, 1), gm.point(2, 2)", "<m>", "exec"), ns)
    assert ns["a"].id == "a"
    assert ns["b"].id == "b"


def test_attribute_target_falls_back():
    class Holder:
        pass

    h = Holder()
    with gm.Store():
        h.p = gm.point(1, 1)
    assert h.p.id == "p-0"


def test_chained_assignment_names_every_target():
    with gm.Store() as s:
        a = b = gm.point(1, 1)
    assert a is b
    assert a.id == "a"  # the python object carries the FIRST target's id
    assert s.nodes["b"].id == "b"  # each extra target gets its own cloned node
    assert gm.emit(s) == "a = \\point 1 1\nb = \\point 1 1"


def test_chained_assignment_triple_and_taken_names():
    with gm.Store() as s:
        x = y = z = gm.scalar(2)
    assert x.id == "x"
    assert gm.emit(s).splitlines() == [
        "x = \\scalar 2",
        "y = \\scalar 2",
        "z = \\scalar 2",
    ]
    with gm.Store() as s2:
        gm.point(0, 0, out="a")
        a = b = gm.point(1, 1)  # "a" taken → object gets "b", no extra
    assert a.id == "b"
    assert gm.emit(s2).splitlines()[-1] == "b = \\point 1 1"


def test_walrus_value_assigned_names_both():
    with gm.Store() as s:
        d = (w := gm.point(1, 2))
    assert d is w
    assert w.id == "w"
    assert gm.emit(s) == "w = \\point 1 2\nd = \\point 1 2"


def test_helper_function_indirection_falls_back():
    def make(x):
        return gm.point(x, 0)

    with gm.Store():
        p = make(3)
    assert p.id == "p-0"


def test_inferred_duplicate_falls_back_but_explicit_still_raises():
    with gm.Store():
        gm.point(0, 0, out="a")
        a = gm.point(1, 1)  # inferred "a" is taken → auto id, no error
        assert a.id == "p-0"
        with pytest.raises(ValueError, match="already exists"):
            gm.point(2, 2, out="a")


def test_inferred_numbered_name_reserves_counter():
    with gm.Store():
        p_5 = gm.point(0, 0)  # → "p-5", must push the auto counter past 5
        nxt = [gm.point(1, 1)][0]
    assert p_5.id == "p-5"
    assert nxt.id == "p-6"


def test_imperative_commands_unaffected():
    with gm.Store() as s:
        a = gm.point(1, 2)
        result = gm.highlight(a)
    assert getattr(result, "id", None) is None  # no output id, despite the target
    assert gm.emit(s).splitlines()[-1] == "\\highlight a"


def test_macro_invocation_infers_id():
    gm.load_macros([{"macro": "double x", "commands": ["\\mul x 2"]}], name="t-infer")
    try:
        with gm.Store() as st:
            a = gm.scalar(3)
            dbl = gm.double(a)
            assert dbl is st.nodes["dbl"]
        assert gm.emit(st) == "a = \\scalar 3\ndbl = \\double a"
    finally:
        gm.unload_macros("t-infer")


def test_macro_body_replay_is_never_inferred():
    # Body lines replay with engine-style ids; the invocation is the only
    # place inference applies. Round-trip parity with parse must hold.
    with gm.Store() as st:
        gm.parse_dsl("p1 = \\point 1 0")
        gm.cardioid()
    emitted = gm.emit(st)
    with gm.Store() as s2:
        gm.parse_dsl(emitted)
    assert gm.emit(s2) == emitted


def test_parse_replay_is_never_inferred():
    src = "\n".join(["p-0 = \\point 3 4", "num-0 = \\distance p0 p-0"])
    with gm.Store() as s:
        gm.parse_dsl(src)
    assert gm.emit(s) == src


def test_run_generated_infers_from_exec_source():
    code = "\n".join(
        [
            "def build(gm):",
            "    left = gm.point(0, 0)",
            "    right = gm.point(4, 0)",
            "    gm.distance(left, right)",
        ]
    )
    result = gm.run_generated(code)
    assert result.ok, result.error
    assert result.dsl == [
        "left = \\point 0 0",
        "right = \\point 4 0",
        "num-0 = \\distance left right",
    ]


def test_exec_from_string_infers():
    # bytecode-based inference needs no source: bare exec behaves like a file
    ns = {"gm": gm}
    with gm.Store() as s:
        exec(compile("p = gm.point(3, 4)", "<no-source>", "exec"), ns)
    assert ns["p"].id == "p"
    assert gm.emit(s) == "p = \\point 3 4"


def test_python_dash_c_infers():
    import subprocess
    import sys

    script = "import pygeomatic as gm; p = gm.point(2, 3); print(p.id)"
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "p"


def test_interactive_repl_infers():
    import subprocess
    import sys

    session = "import pygeomatic as gm\np = gm.point(2, 3)\nprint(p.id)\n"
    # -i forces REPL statement-at-a-time compilation even with piped stdin
    proc = subprocess.run(
        [sys.executable, "-i", "-q"],
        input=session,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "p"
