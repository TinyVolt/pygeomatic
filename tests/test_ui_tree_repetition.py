"""Repetition in a gm.ui tree needs no new element.

`gm.array` already supplies it, in three patterns. They are tested here because
they are the documented answer to "how do I make N rows", and a model writing
this python needs them to keep working.

What is NOT expressible is unbounded growth: `\\array` fixes its shape when it
computes, there is no append or resize command, and `__len__` raises rather than
guess — the loop body decides how many commands get emitted. So a reader cannot
create rows the author did not budget for. The last test pins that boundary.
"""

import json
import re

import pytest

from pygeomatic import ArticleError, compile_article


def fence(code: str) -> str:
    return f"```pygeomatic\n{code}\n```\n"


def one_tree(code: str) -> dict:
    compiled = compile_article(fence(code))
    match = re.search(r"<!-- ui:v1\n(.*?)\n-->", compiled, re.S)
    assert match, f"no ui:v1 manifest in {compiled!r}"
    return json.loads(match.group(1))["t0"]


def commands_of(code: str) -> str:
    """The whole compiled article, for asserting which DSL was emitted."""
    return compile_article(fence(code))


# ---------------------------------------------------------------------------
# 1. Unroll at authoring time
# ---------------------------------------------------------------------------


def test_a_python_loop_over_an_array_emits_one_element_per_item():
    tree = one_tree(
        "xs = gm.array(gm.scalar(1), gm.scalar(2), gm.scalar(3))\n"
        "with gm.ui.col():\n"
        "    for i in range(len(xs)):\n"
        '        gm.ui.label(f"item ${{{xs[i].id}}}")\n'
    )
    assert len(tree["children"]) == 3
    assert all(child["tag"] == "label" for child in tree["children"])


def test_iterating_an_array_directly_also_unrolls():
    tree = one_tree(
        "xs = gm.array(gm.scalar(1), gm.scalar(2))\n"
        "with gm.ui.col():\n"
        "    for el in xs:\n"
        '        gm.ui.label(f"${{{el.id}}}")\n'
    )
    assert len(tree["children"]) == 2


# ---------------------------------------------------------------------------
# 2. A reader-chosen element
# ---------------------------------------------------------------------------


def test_indexing_with_a_scalar_node_records_get_array_element():
    """`arr[k]` where k is a control's node: one row showing whichever item the
    reader picks. The index is a live node, so the row follows it."""
    compiled = commands_of(
        "with gm.onpageload():\n"
        "    xs = gm.array(gm.scalar(10), gm.scalar(20), gm.scalar(30))\n"
        "    k = gm.ui.number(0, 2, value=0)\n"
        "    chosen = xs[k]\n"
        "    with gm.ui.col():\n"
        '        gm.ui.label("picked ${chosen}")\n'
    )
    assert "\\get-array-element" in compiled


def test_the_chosen_element_is_a_real_node_the_tree_can_read():
    tree = one_tree(
        "with gm.onpageload():\n"
        "    xs = gm.array(gm.scalar(10), gm.scalar(20))\n"
        "    k = gm.ui.number(0, 1, value=0)\n"
        "    chosen = xs[k]\n"
        "    with gm.ui.col():\n"
        '        gm.ui.label("picked ${chosen}")\n'
    )
    # It passed the compiler's reference check, which only accepts a node the
    # article actually defines.
    assert tree["children"][0]["text"] == "picked ${chosen}"


# ---------------------------------------------------------------------------
# 3. A bounded dynamic count
# ---------------------------------------------------------------------------


def test_rows_can_be_gated_on_a_count_the_reader_controls():
    """Emit the maximum, gate each row on `i < n`. Rows appear and vanish as the
    reader drags `n`, with no repetition primitive involved."""
    tree = one_tree(
        "with gm.onpageload():\n"
        "    n = gm.ui.number(0, 3, value=2)\n"
        "    with gm.ui.col():\n"
        "        for i in range(3):\n"
        "            with when(gm.cond.lt(i, n)):\n"
        '                gm.ui.label(f"row {i}")\n'
    )
    gates = tree["children"]
    assert [g["tag"] for g in gates] == ["when", "when", "when"]
    assert gates[0]["cond"] == {"op": "lt", "a": {"const": 0.0}, "b": {"node": "n"}}
    assert gates[2]["cond"] == {"op": "lt", "a": {"const": 2.0}, "b": {"node": "n"}}
    assert [g["children"][0]["text"] for g in gates] == ["row 0", "row 1", "row 2"]


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


def test_an_array_of_unknown_length_refuses_to_unroll():
    """`__len__` raises rather than answer 0, because answering 0 would drop the
    author's loop body from the DSL instead of reporting anything."""
    from pygeomatic.nodes import Array

    unknown = Array._new(element_type="Scalar", shape_unknown=True)
    with pytest.raises(TypeError, match="unknown at record time"):
        len(unknown)
