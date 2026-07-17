"""Numeric spot checks for the compute-and-record implementations."""

import numpy as np
import pytest

import pygeomatic as gm


@pytest.fixture(autouse=True)
def fresh_store():
    with gm.Store() as s:
        yield s


def test_point_and_distance():
    a = gm.point(0, 0)
    b = gm.point(3, 4)
    assert float(gm.distance(a, b)) == pytest.approx(5.0)


def test_mid_point_and_prop_access():
    a = gm.point(1, 2)
    c = gm.circle(a, 3)
    m = gm.mid_point(c.center, gm.point(3, 4))
    assert m.numeric == pytest.approx((2.0, 3.0))
    # prop chains render as DSL property access
    assert c.center.x.ref.render() == f"{c.id}.center.x"


def test_linspace_reduce_and_softmax():
    xs = gm.linspace(0, 1, 5)
    assert np.allclose(xs.numeric, [0, 0.25, 0.5, 0.75, 1.0])
    assert float(gm.reduce_sum(xs)) == pytest.approx(2.5)
    sm = gm.softmax(gm.array(1, 2, 3))
    assert float(np.sum(sm.numeric)) == pytest.approx(1.0)


def test_reduce_along_dim():
    m = gm.reshape(gm.arange(0, 6, 1), 2, 3)
    rows = gm.reduce_sum(m, 1)
    assert np.allclose(rows.numeric, [3.0, 12.0])


def test_complex_mul_and_overload_dispatch():
    z = gm.complex_(1, 2)
    z2 = gm.mul(z, z)
    assert complex(z2) == pytest.approx(complex(-3, 4))
    s = gm.add(2, 3, 4)
    assert float(s) == pytest.approx(9.0)
    mixed = gm.add(gm.scalar(1), z)  # scalar promoted to 1+0i
    assert complex(mixed) == pytest.approx(complex(2, 2))
    assert float(gm.abs_(gm.complex_(3, 4))) == pytest.approx(5.0)


def test_fft_roundtrip():
    arr = gm.array(gm.scalar(1), gm.scalar(2), gm.scalar(3), gm.scalar(4))
    back = gm.ifft(gm.fft(arr))
    assert np.allclose([complex(e) for e in back._elements], [1, 2, 3, 4])


def test_intersection_line_circle_ordering():
    line = gm.line(gm.point(-5, 0), gm.point(5, 0))
    circ = gm.circle(gm.point(0, 0), 3)
    pts = gm.intersection_line_circle(line, circ)
    # t1 = (-b + sqrt(disc)) / 2a first, matching the TS ordering
    assert pts._elements[0].numeric == pytest.approx((3.0, 0.0))
    assert pts._elements[1].numeric == pytest.approx((-3.0, 0.0))


def test_triangle_centers():
    tri = gm.triangle(gm.point(0, 0), gm.point(4, 0), gm.point(0, 3))
    assert gm.centroid(tri).numeric == pytest.approx((4 / 3, 1.0))
    assert gm.circumcenter(tri).numeric == pytest.approx((2.0, 1.5))
    assert float(gm.area_triangle(tri)) == pytest.approx(6.0)


def test_rotate_and_translate_mutate():
    p = gm.point(1, 0)
    gm.rotate(p, gm.point(0, 0), 90)  # degrees
    assert p.numeric == pytest.approx((0.0, 1.0), abs=1e-12)
    gm.translate(p, 2, 3)
    assert p.numeric == pytest.approx((2.0, 4.0), abs=1e-12)


def test_polynomial_evaluation():
    poly = gm.polynomial(1, 2, 3)  # 1 + 2x + 3x^2
    assert float(gm.evaluate_polynomial(poly, 2)) == pytest.approx(17.0)


def test_binary_conversions():
    assert gm.int_to_bin(-6).numeric == "11111010"
    assert gm.int_to_bin(-6, 8, False).numeric == "11111001"
    assert gm.uint_to_bin(6).numeric == "00000110"
    assert float(gm.bin_to_dec_twos_complement(gm.text("11111010"))) == pytest.approx(-6)
    assert gm.fp_to_bin(1.0, 32).numeric == "0" + "01111111" + "0" * 23


def test_filter_mask():
    arr = gm.array(10, 20, 30, 40)
    mask = gm.array(gm.bool_(1), gm.bool_(0), gm.bool_(1), gm.bool_(0))
    kept = gm.filter_(arr, mask)
    assert np.allclose(kept.numeric, [10, 30])


def test_infix_arithmetic_records_overload_commands():
    with gm.Store() as s:
        a = gm.scalar(1)
        b = gm.scalar(2)
        c = a + b
        assert float(c) == 3.0
    assert gm.emit(s).splitlines()[-1] == "c = \\add a b"


def test_infix_rejected_for_non_arithmetic_nodes():
    p = gm.point(1, 2)
    q = gm.point(3, 4)
    with pytest.raises(TypeError, match="Point nodes"):
        p + q  # noqa: B018
    a = gm.scalar(1)
    with pytest.raises(TypeError, match="\\*\\*"):
        a**2  # noqa: B018


def test_identifier_validation():
    with pytest.raises(ValueError, match="underscores"):
        gm.point(1, 2, out="my_point")
    p = gm.point(1, 2, out="fwd-traj0")
    assert p.id == "fwd-traj0"


def test_engine_auto_shaped_ids_rejected():
    # `num0 = \mul p0.x scale` lets the engine's p0.x accessor claim num0
    # first, then the assignment clobbers its own input → reactive cycle.
    for bad in ("num0", "p3", "text1", "arr12", "circ0"):
        with pytest.raises(ValueError, match="auto-generated"):
            gm.point(1, 2, out=bad)
    # dashed and descriptive ids stay legal
    assert gm.point(1, 2, out="p-3").id == "p-3"
    assert gm.point(1, 2, out="scale-then-rotate").id == "scale-then-rotate"
