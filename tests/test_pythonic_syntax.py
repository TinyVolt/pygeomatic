"""Pythonic authoring syntax: multi-target assignment, infix operators with
variadic fusion, array indexing/iteration. All bytecode-driven, so behavior
must be identical in files, exec'd strings, the REPL, and `python -c`.
"""

import subprocess
import sys

import pytest

import pygeomatic as gm


# --- multi-target assignment -------------------------------------------------


def test_multi_target_three_and_four_arity_function_scope():
    with gm.Store():
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        w, x, y, z = gm.point(1, 1), gm.point(2, 2), gm.point(3, 3), gm.point(4, 4)
    assert [n.id for n in (a, b, c)] == ["a", "b", "c"]
    assert [n.id for n in (w, x, y, z)] == ["w", "x", "y", "z"]


def test_multi_target_module_scope_any_arity():
    ns = {"gm": gm}
    src = "\n".join(
        [
            "a, b = gm.scalar(1), gm.scalar(2)",
            "c, d, e = gm.scalar(3), gm.scalar(4), gm.scalar(5)",
            "p, q, r, s, t = (gm.point(1, 1), gm.point(2, 2), gm.point(3, 3),"
            " gm.point(4, 4), gm.point(5, 5))",
        ]
    )
    with gm.Store():
        exec(compile(src, "<m>", "exec"), ns)
    for name in ("a", "b", "c", "d", "e", "p", "q", "r", "s", "t"):
        assert ns[name].id == name, f"{name} got {ns[name].id}"


def test_multi_target_mixed_call_and_literal():
    with gm.Store():
        a, k = gm.point(1, 1), 5
    assert a.id == "a"
    assert k == 5


def test_multi_target_values_not_crossed():
    with gm.Store():
        a, b = gm.scalar(10), gm.scalar(20)
    assert float(a) == 10.0
    assert float(b) == 20.0


def test_swap_of_existing_nodes_records_nothing():
    with gm.Store() as s:
        a, b = gm.scalar(1), gm.scalar(2)
        a, b = b, a
    assert len(gm.emit(s).splitlines()) == 2
    assert float(a) == 2.0


# --- infix operators ----------------------------------------------------------


def test_each_operator_records_and_computes():
    with gm.Store() as s:
        a = gm.scalar(8)
        b = gm.scalar(2)
        add = a + b
        sub = a - b
        mul = a * b
        div = a / b
        neg = -a
    assert [float(n) for n in (add, sub, mul, div, neg)] == [10.0, 6.0, 16.0, 4.0, -8.0]
    assert gm.emit(s).splitlines()[2:] == [
        "add = \\add a b",
        "sub = \\sub a b",
        "mul = \\mul a b",
        "div = \\div a b",
        "neg = \\neg a",
    ]


def test_number_literals_on_either_side():
    with gm.Store() as s:
        a = gm.scalar(3)
        left = a * 2
        right = 2 * a
        rsub = 10 - a
        rdiv = 12 / a
    assert [float(n) for n in (left, right, rsub, rdiv)] == [6.0, 6.0, 7.0, 4.0]
    assert gm.emit(s).splitlines()[1:] == [
        "left = \\mul a 2",
        "right = \\mul 2 a",
        "rsub = \\sub 10 a",
        "rdiv = \\div 12 a",
    ]


def test_operator_on_property_accessor():
    with gm.Store() as s:
        p = gm.point(3, 4)
        shifted = p.x + 1
    assert float(shifted) == 4.0
    assert gm.emit(s).splitlines()[-1] == "shifted = \\add p.x 1"


def test_complex_operands_route_to_complex_kernel():
    with gm.Store():
        z = gm.complex_(1, 2)
        w = z * gm.complex_(0, 1)
    assert complex(w) == complex(-2, 1)


def test_array_broadcasting():
    with gm.Store() as s:
        arr = gm.array(1, 2, 3)
        doubled = arr * 2
    assert list(doubled.numeric) == [2.0, 4.0, 6.0]
    assert gm.emit(s).splitlines()[-1] == "doubled = \\mul arr 2"


def test_augmented_assignment_raises():
    # `acc += 2` would rebind the python variable while DSL node `acc` keeps
    # its old value — refused so results can't silently diverge.
    with gm.Store() as s:
        acc = gm.scalar(1)
        with pytest.raises(TypeError, match="in-place \\+="):
            acc += 2
        with pytest.raises(TypeError, match="in-place \\*="):
            acc *= 2
    assert gm.emit(s) == "acc = \\scalar 1"  # nothing was recorded


def test_unsupported_operand_kinds():
    a = gm.scalar(1)
    p = gm.point(1, 2)
    with pytest.raises(TypeError, match="Point nodes"):
        a + p  # noqa: B018
    with pytest.raises(TypeError, match="Point nodes"):
        -p  # noqa: B018
    with pytest.raises(TypeError):
        a + "s"  # noqa: B018
    with pytest.raises(TypeError):
        a + True  # noqa: B018
    with pytest.raises(TypeError, match="\\*\\*"):
        a**2  # noqa: B018
    with pytest.raises(TypeError, match="@"):
        a @ a  # noqa: B018


# --- variadic fusion ----------------------------------------------------------


def test_add_chain_fuses_to_one_line():
    with gm.Store() as s:
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        d = a + b + c
    assert float(d) == 6.0
    assert gm.emit(s).splitlines()[-1] == "d = \\add a b c"
    assert len(s.commands) == 4


def test_long_chain_and_mul_fusion():
    with gm.Store() as s:
        a, b, c, e = gm.scalar(1), gm.scalar(2), gm.scalar(3), gm.scalar(4)
        total = a + b + c + e + 5
        prod = a * b * c
    assert float(total) == 15.0
    assert float(prod) == 6.0
    lines = gm.emit(s).splitlines()
    assert lines[-2] == "total = \\add a b c e 5"
    assert lines[-1] == "prod = \\mul a b c"


def test_parenthesized_groups_fuse():
    with gm.Store() as s:
        a, b, c, e = gm.scalar(1), gm.scalar(2), gm.scalar(3), gm.scalar(4)
        d = (a + b) + (c + e)
    assert float(d) == 10.0
    assert gm.emit(s).splitlines()[-1] == "d = \\add a b c e"


def test_no_fusion_across_different_keywords():
    with gm.Store() as s:
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        d = a + b * c
    assert float(d) == 7.0
    assert gm.emit(s).splitlines()[-2:] == [
        "num-0 = \\mul b c",
        "d = \\add a num-0",
    ]


def test_named_intermediate_is_not_fused():
    with gm.Store() as s:
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        d = (t := a + b) + c
    assert t.id == "t"
    assert float(d) == 6.0
    assert gm.emit(s).splitlines()[-2:] == ["t = \\add a b", "d = \\add t c"]


def test_explicit_nested_calls_are_not_fused():
    with gm.Store() as s:
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        gm.add(gm.add(a, b), c)
    assert gm.emit(s).splitlines()[-2:] == [
        "num-0 = \\add a b",
        "num-1 = \\add num-0 c",
    ]


def test_fusion_rewinds_the_auto_counter():
    with gm.Store():
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        d = a + b + c  # intermediate briefly claims num-0, then is released
        nxt = [gm.add(a, b)][0]
    assert d.id == "d"
    assert nxt.id == "num-0"


def test_subtraction_chain_does_not_fuse():
    with gm.Store() as s:
        a, b, c = gm.scalar(10), gm.scalar(3), gm.scalar(2)
        d = a - b - c
    assert float(d) == 5.0
    assert gm.emit(s).splitlines()[-2:] == [
        "num-0 = \\sub a b",
        "d = \\sub num-0 c",
    ]


# --- indexing / iteration / len -----------------------------------------------


def test_indexing_records_get_array_element():
    with gm.Store() as s:
        arr = gm.array(10, 20, 30)
        x = arr[1]
    assert float(x) == 20.0
    assert gm.emit(s).splitlines()[-1] == "x = \\get-array-element arr 1"


def test_indexing_with_scalar_node():
    with gm.Store() as s:
        arr = gm.array(10, 20, 30)
        i = gm.scalar(2)
        x = arr[i]
    assert float(x) == 30.0
    assert gm.emit(s).splitlines()[-1] == "x = \\get-array-element arr i"


def test_negative_literal_index_is_normalized():
    with gm.Store() as s:
        arr = gm.array(10, 20, 30)
        last = arr[-1]
    assert float(last) == 30.0
    assert gm.emit(s).splitlines()[-1] == "last = \\get-array-element arr 2"


def test_slice_setitem_and_bad_index_error():
    with gm.Store():
        arr = gm.array(10, 20, 30)
        with pytest.raises(TypeError, match="slice"):
            arr[1:2]  # noqa: B018
        with pytest.raises(TypeError, match="element-assignment"):
            arr[0] = gm.scalar(1)
        with pytest.raises(TypeError, match="int or a Scalar"):
            arr["x"]  # noqa: B018
        with pytest.raises(IndexError):
            arr[7]  # noqa: B018


def test_len_and_loop_unrolling():
    with gm.Store() as s:
        arr = gm.array(5, 6, 7)
        assert len(arr) == 3
        picked = [arr[k] for k in range(len(arr))]
    assert [float(x) for x in picked] == [5.0, 6.0, 7.0]
    # len() records nothing; each arr[k] records one command
    assert len(s.commands) == 1 + 3


def test_iteration_via_sequence_protocol():
    with gm.Store() as s:
        arr = gm.array(1, 2)
        els = list(arr)
    assert [float(x) for x in els] == [1.0, 2.0]
    assert [c.keyword for c in s.commands] == ["array"] + ["get-array-element"] * 2


# --- cross-environment consistency + round-trip --------------------------------


def test_emitted_scene_round_trips_through_parse():
    with gm.Store() as s:
        a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)
        d = a + b + c
        arr = gm.array(a, b, d)
        x = arr[-1]
        gm.highlight(x)
    emitted = gm.emit(s)
    with gm.Store() as s2:
        gm.parse_dsl(emitted)
    assert gm.emit(s2) == emitted


def test_python_dash_c_names_operator_results():
    script = (
        "import pygeomatic as gm; a, b = gm.scalar(2), gm.scalar(3); "
        "c = a + b + 1; print(a.id, b.id, c.id)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "a b c"


def test_interactive_repl_names_operator_results():
    session = "\n".join(
        [
            "import pygeomatic as gm",
            "a, b = gm.scalar(2), gm.scalar(3)",
            "c = a + b",
            "x = gm.array(1, 2, 3)[-1]",
            "print(a.id, b.id, c.id, x.id)",
            "",
        ]
    )
    proc = subprocess.run(
        [sys.executable, "-i", "-q"],
        input=session,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "a b c x"


def test_run_generated_supports_all_new_syntax():
    code = "\n".join(
        [
            "def build(gm):",
            "    a, b, c = gm.scalar(1), gm.scalar(2), gm.scalar(3)",
            "    total = a + b + c",
            "    arr = gm.array(a, b, total)",
            "    last = arr[-1]",
            "    gm.highlight(last)",
        ]
    )
    result = gm.run_generated(code)
    assert result.ok, result.error
    assert result.dsl == [
        "a = \\scalar 1",
        "b = \\scalar 2",
        "c = \\scalar 3",
        "total = \\add a b c",
        "arr = \\array a b total",
        "last = \\get-array-element arr 2",
        "\\highlight last",
    ]
