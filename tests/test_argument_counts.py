import pytest

import pygeomatic as gm


@pytest.fixture
def store():
    with gm.Store() as s:
        yield s


def _corners():
    return [gm.point(0, 0), gm.point(4, 0), gm.point(0, 3)]


@pytest.mark.parametrize(
    "call, message",
    [
        (
            lambda ring, a: gm.polygon(ring),
            "\\polygon needs at least 3 arguments (vertex1 vertex2 vertex3...), got 1",
        ),
        (
            lambda ring, a: gm.convex_hull(ring),
            "\\convex-hull needs at least 2 arguments (point1 point2...), got 1",
        ),
        (
            lambda ring, a: gm.polyline(ring),
            "\\polyline needs at least 2 arguments (point1 point2...), got 1",
        ),
        (lambda ring, a: gm.min_(a), "\\min needs at least 2 arguments (a b...), got 1"),
        (lambda ring, a: gm.max_(a), "\\max needs at least 2 arguments (a b...), got 1"),
        (lambda ring, a: gm.add(a), "\\add needs at least 2 arguments (a b...), got 1"),
        (lambda ring, a: gm.mul(a), "\\mul needs at least 2 arguments (a b...), got 1"),
        (
            lambda ring, a: gm.reshape(a),
            "\\reshape needs at least 2 arguments (array dim...), got 1",
        ),
    ],
)
def test_too_few_arguments_with_an_array(store, call, message):
    ring = gm.array(*_corners())
    a = gm.array(1, 2, 3)
    with pytest.raises(TypeError) as err:
        call(ring, a)
    assert str(err.value).startswith(message)
    assert "is an Array" in str(err.value)
    assert "(*ring)" in str(err.value) or "(*a)" in str(err.value)


def test_hint_names_the_python_function(store):
    ring = gm.array(*_corners())
    with pytest.raises(TypeError, match=r"did you mean gm\.convex_hull\(\*ring\)\?"):
        gm.convex_hull(ring)
    a = gm.array(1, 2)
    with pytest.raises(TypeError, match=r"did you mean gm\.min_\(\*a\)\?"):
        gm.min_(a)


def test_hint_uses_underscores_for_dashed_ids(store):
    corner_list = gm.array(*_corners())
    with pytest.raises(TypeError, match=r"gm\.polygon\(\*corner_list\)"):
        gm.polygon(corner_list)


def test_too_few_arguments_without_an_array_has_no_hint(store):
    with pytest.raises(TypeError) as err:
        gm.and_()
    assert str(err.value) == "\\and needs at least 1 argument (values...), got 0"


def test_unpacking_works(store):
    corners = _corners()
    tri = gm.polygon(*corners)
    hull = gm.convex_hull(*corners)
    a = gm.array(1, 2, 3)
    low = gm.min_(*a)
    lines = gm.emit().splitlines()
    ids = " ".join(p.id for p in corners)
    assert f"tri = \\polygon {ids}" in lines
    assert f"hull = \\convex-hull {ids}" in lines
    assert lines[-1].startswith("low = \\min ")
    assert len(lines[-1].split()) == 6


@pytest.mark.parametrize("fn", [gm.trail, gm.param, gm.highlight, gm.hide, gm.show, gm.remove])
def test_imperative_commands_need_one_value(store, fn):
    with pytest.raises(TypeError, match=r"needs at least 1 argument"):
        fn()


def test_gradient_descent_step_takes_no_arguments(store):
    w = gm.scalar(1)
    gm.param(w)
    gm.gradient_descent_step()
    assert gm.emit().splitlines()[-1] == "\\gradient-descent-step"


def test_gradient_descent_step_rejects_an_array(store):
    a = gm.array(1, 2, 3)
    gm.param(a)
    with pytest.raises(
        TypeError,
        match=r"Pass single Scalars or Points, or call gm\.gradient_descent_step\(\) with no arguments",
    ):
        gm.gradient_descent_step(a)
    assert "\\gradient-descent-step a" not in gm.emit()


def test_gradient_descent_step_still_takes_single_nodes(store):
    w = gm.scalar(1)
    p = gm.point(1, 2)
    gm.param(w, p)
    gm.gradient_descent_step(w, p)
    assert gm.emit().splitlines()[-1] == "\\gradient-descent-step w p"
