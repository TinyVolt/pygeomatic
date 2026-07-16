"""Tape → DSL emission round-trips."""

import pytest

import pygeomatic as gm


def test_emit_small_scene():
    with gm.Store() as s:
        a = gm.point(1, 2, out="a")
        b = gm.point(4, 6)
        gm.distance(a, b)
        c = gm.circle(a, 3)
        gm.mid_point(c.center, b)
        gm.highlight(a, b)
        gm.text("hello world")
    assert gm.emit(s) == "\n".join(
        [
            "a = \\point 1 2",
            "b = \\point 4 6",
            "num-0 = \\distance a b",
            "c = \\circle a 3",
            "p-0 = \\mid-point c.center b",
            "\\highlight a b",
            'text-0 = \\text "hello world"',
        ]
    )


def test_emit_numbers_never_scientific():
    with gm.Store() as s:
        gm.point(0.0000001, 12345678.5)
    line = gm.emit(s)
    assert "e" not in line.lower().replace("point", "")
    assert line == "p-0 = \\point 0.0000001 12345678.5"


def test_implicit_text_precedes_annotation():
    with gm.Store() as s:
        a = gm.point(0, 0)
        gm.annotate_pin(a, "origin")
    assert gm.emit(s) == "\n".join(
        [
            "a = \\point 0 0",
            'text-0 = \\text "origin"',
            "pin-0 = \\annotate-pin a text-0",
        ]
    )


def test_omitted_defaults_are_omitted_from_line():
    with gm.Store() as s:
        gm.linspace(0, 1)  # n omitted → engine default 10
        gm.reduce_sum(gm.array(1, 2))  # dim omitted
    lines = gm.emit(s).splitlines()
    assert lines[0] == "arr-0 = \\linspace 0 1"
    assert lines[2] == "num-0 = \\reduce-sum arr-1"


def test_explicit_id_reserves_counter():
    with gm.Store():
        gm.point(0, 0, out="p-5")
        # inside a list literal so no assignment-target name is inferred
        nodes = [gm.point(1, 1)]
    assert nodes[0].id == "p-6"


def test_variadic_and_imperative_forms():
    with gm.Store() as s:
        a = gm.scalar(1)
        b = gm.scalar(2)
        c = gm.scalar(3)
        gm.add(a, b, c)
        gm.clear()
    lines = gm.emit(s).splitlines()
    assert lines[3] == "num-0 = \\add a b c"
    assert lines[4] == "\\clear"


def test_duplicate_out_id_rejected():
    with gm.Store():
        gm.point(0, 0, out="a")
        with pytest.raises(ValueError, match="already exists"):
            gm.point(1, 1, out="a")
