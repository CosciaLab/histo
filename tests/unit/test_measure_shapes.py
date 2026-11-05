"""Tests for measure_shapes.py: polygon-exact morphology features."""

import numpy as np
import pytest
from measure_shapes import MIN_CIRCULARITY_AREA, shape_features

pd = pytest.importorskip("pandas", reason="needs pandas")
pytest.importorskip("shapely", reason="needs shapely")
from shapely import affinity  # noqa: E402
from shapely.geometry import MultiPolygon, Point, Polygon, box  # noqa: E402


def ellipse(a, b, x=100.0, y=200.0):
    """Ellipse with semi-axes a, b, centred at (x, y)."""
    return affinity.translate(affinity.scale(Point(0, 0).buffer(1, quad_segs=256), a, b), x, y)


def one(geom, prefix="cell"):
    return shape_features([geom], pd.Index(["c0"]), prefix).iloc[0]


def test_ellipse_axes_and_eccentricity():
    f = one(ellipse(20, 10))
    assert f.cell_major_axis_length == pytest.approx(40, rel=1e-3)
    assert f.cell_minor_axis_length == pytest.approx(20, rel=1e-3)
    assert f.cell_eccentricity == pytest.approx(np.sqrt(1 - 0.25), rel=1e-3)


def test_rotation_does_not_change_axes():
    f = one(affinity.rotate(ellipse(20, 10), 30, origin="centroid"))
    assert f.cell_major_axis_length == pytest.approx(40, rel=1e-3)
    assert f.cell_minor_axis_length == pytest.approx(20, rel=1e-3)
    assert f.cell_eccentricity == pytest.approx(np.sqrt(0.75), rel=1e-3)


def test_slide_scale_coordinates_keep_precision():
    f = one(ellipse(20, 10, x=1e5, y=1e5))
    assert f.cell_major_axis_length == pytest.approx(40, rel=1e-3)


def test_disc_circularity_near_one():
    f = one(ellipse(10, 10))
    assert f.cell_circularity == pytest.approx(1, rel=1e-3)
    assert f.cell_eccentricity < 1e-3


def test_square_circularity_and_solidity():
    f = one(box(0, 0, 10, 10))
    assert f.cell_circularity == pytest.approx(np.pi / 4)
    assert f.cell_solidity == pytest.approx(1)
    assert f.cell_perimeter == pytest.approx(40)


def test_l_shape_solidity():
    g = box(0, 0, 10, 2).union(box(0, 0, 2, 10))
    f = one(g)
    assert f.cell_solidity == pytest.approx(g.area / g.convex_hull.area)
    assert f.cell_solidity < 1


def test_hole_subtracted():
    f = one(box(0, 0, 20, 20).difference(box(5, 5, 15, 15)))
    assert f.cell_area == pytest.approx(300)
    assert f.cell_eccentricity == pytest.approx(0, abs=1e-6)


def test_multipolygon_sums_parts():
    f = one(MultiPolygon([box(0, 0, 4, 4), box(10, 0, 14, 4)]))
    assert f.cell_area == pytest.approx(32)
    assert f.cell_major_axis_length > f.cell_minor_axis_length


def test_tiny_shape_circularity_nan():
    assert box(0, 0, 5, 5).area < MIN_CIRCULARITY_AREA
    f = one(box(0, 0, 5, 5))
    assert np.isnan(f.cell_circularity)
    assert f.cell_area == pytest.approx(25)


def test_none_and_empty_are_nan():
    out = shape_features([None, Polygon()], pd.Index(["a", "b"]), "cell")
    assert out.isna().all().all()
    assert list(out.index) == ["a", "b"]


def test_prefix_and_index():
    out = shape_features([box(0, 0, 10, 10), box(0, 0, 20, 5)], pd.Index(["x", "y"]), "nucleus")
    assert list(out.index) == ["x", "y"]
    assert all(c.startswith("nucleus_") for c in out.columns)
    assert len(out.columns) == 7
    assert (out.dtypes == np.float64).all()
