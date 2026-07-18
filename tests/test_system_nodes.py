"""System (default) nodes: seeded per store, referenceable as gm.<attr>."""

import pytest

import pygeomatic as gm


def test_every_system_node_seeded_in_fresh_store():
    with gm.Store() as s:
        for node_id in gm.SYSTEM_NODE_IDS:
            assert node_id in s.nodes


def test_attribute_access_resolves_active_store():
    with gm.Store() as s:
        assert gm.p0 is s.nodes["p0"]
        assert gm.T is s.nodes["T"]
        assert gm.F is s.nodes["F"]
        assert gm.learning_rate is s.nodes["learning-rate"]
        assert gm.grid_bg_color is s.nodes["grid-bg-color"]


def test_attribute_access_tracks_reassignment():
    with gm.Store() as s:
        before = gm.p0
        replaced = gm.point(3, 4, out="p0")
        assert gm.p0 is replaced
        assert gm.p0 is not before
        assert s.nodes["p0"] is replaced


def test_system_node_usable_as_argument():
    with gm.Store() as s:
        gm.line(gm.p0, gm.point(1, 1, out="q"))
    assert gm.emit(s) == "\n".join(
        [
            "q = \\point 1 1",
            "line-0 = \\line p0 q",
        ]
    )


def test_system_nodes_record_no_commands():
    with gm.Store() as s:
        pass
    assert gm.emit(s) == ""


def test_unknown_attribute_still_raises():
    with pytest.raises(AttributeError):
        gm.not_a_real_attribute


def test_dir_lists_system_node_attrs():
    names = dir(gm)
    assert "p0" in names
    assert "learning_rate" in names
    assert "grid_points" in names
