"""gm.shuffle: mirror of `\\shuffle` in array.ts (tinyvolt-web shuffle.test.ts)."""

import numpy as np
import pytest

import pygeomatic as gm


@pytest.fixture(autouse=True)
def fresh_store():
    with gm.Store() as s:
        yield s


def test_key_7_matches_engine_order():
    s = gm.shuffle(gm.array(*range(10)), 7)
    assert s._element_type == "Scalar"
    assert s._shape == (10,)
    assert list(s.numeric) == [6, 5, 8, 1, 2, 3, 4, 7, 9, 0]


def test_axis_1_key_0_matches_engine_order():
    m = gm.reshape(gm.array(0, 1, 10, 11, 20, 21), 3, 2)
    assert list(gm.shuffle(m, 0, 1).numeric.ravel()) == [1, 0, 11, 10, 21, 20]


def test_same_key_same_order_different_key_different_order():
    arr = gm.array(*range(10))
    a, b, c = gm.shuffle(arr, 3), gm.shuffle(arr, 3), gm.shuffle(arr, 4)
    assert np.array_equal(a.numeric, b.numeric)
    assert not np.array_equal(a.numeric, c.numeric)


def test_axis_0_reorders_whole_rows():
    m = gm.reshape(gm.array(0, 1, 10, 11, 20, 21), 3, 2)
    s = gm.shuffle(m, 7, 0)
    assert s._shape == (3, 2)
    rows = s.numeric
    assert all(r[1] == r[0] + 1 for r in rows)
    assert sorted(r[0] for r in rows) == [0, 10, 20]


def test_points_keep_element_type():
    arr = gm.array(gm.point(1, 2), gm.point(3, 4), gm.point(5, 6))
    s = gm.shuffle(arr, 1)
    assert s._element_type == "Point"
    assert sorted(p.numeric[0] for p in s._elements) == [1, 3, 5]


def test_no_key_returns_a_permutation():
    s = gm.shuffle(gm.array(*range(10)))
    assert s._shape == (10,)
    assert s._element_type == "Scalar"
    assert sorted(s.numeric) == list(range(10))


def test_axis_out_of_range_raises():
    with pytest.raises(ValueError, match="axis 1 out of range"):
        gm.shuffle(gm.array(1, 2, 3), 7, 1)


def test_emit_and_parse_round_trip(fresh_store):
    arr = gm.array(1, 2, 3, out="arr")
    gm.shuffle(arr, out="s1")
    keyed = gm.shuffle(arr, 7, out="s2")
    gm.shuffle(arr, 7, 0, out="s3")
    dsl = gm.emit(fresh_store)
    lines = dsl.splitlines()
    assert lines[1] == "s1 = \\shuffle arr"
    assert lines[2] == "s2 = \\shuffle arr 7"
    assert lines[3] == "s3 = \\shuffle arr 7 0"
    with gm.Store() as s2:
        gm.parse_dsl(dsl)
        assert gm.emit(s2) == dsl
        assert np.array_equal(s2.nodes["s2"].numeric, keyed.numeric)
