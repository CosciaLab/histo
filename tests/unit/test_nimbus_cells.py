"""Tiled Nimbus runner core, tested with a fake model."""

import numpy as np
import pytest
from shapely.geometry import Polygon, box

import nimbus_cells as nc

MARGIN = 8


def identity(_ch, x, _lab):
    return x


def grid_cells(n=6, step=20, size=10, x_off=0, y_off=0):
    geoms = [
        box(x_off + i * step, y_off + j * step, x_off + i * step + size, y_off + j * step + size)
        for j in range(n)
        for i in range(n)
    ]
    return geoms, np.arange(1, len(geoms) + 1)


def run(image, geoms, labels, factors, predict=identity, tile=64, min_window=0, names=None):
    names = names or [f"c{i}" for i in range(image.shape[0])]
    return nc.score_cells(image, geoms, labels, names, factors, predict, tile, MARGIN, min_window)


def test_every_cell_scored_once_for_any_tile_size():
    rng = np.random.default_rng(0)
    image = rng.integers(1, 100, size=(2, 200, 200)).astype(np.float32)
    geoms, labels = grid_cells()
    factors = {"c0": 50.0, "c1": 80.0}
    results = [run(image, geoms, labels, factors, tile=t) for t in (64, 100, 4096)]
    for r in results:
        assert r.shape == (36, 2) and r.dtype == np.float32
        assert not np.isnan(r).any()
    np.testing.assert_allclose(results[0], results[2], atol=1e-6)
    np.testing.assert_allclose(results[1], results[2], atol=1e-6)


def test_border_window_shifted_inward_to_min_window():
    bounds = np.array([[950.0, 950.0, 990.0, 990.0], [10.0, 10.0, 40.0, 40.0]])
    centroids = np.array([[970.0, 970.0], [25.0, 25.0]])
    tiles = nc.assign_tiles(centroids, 300)
    wins = nc.tile_windows(bounds, tiles, 300, 8, 600, (1000, 1000))
    assert len(wins) == 2
    for y0, y1, x0, x1 in wins.values():
        assert y1 - y0 >= 600 and x1 - x0 >= 600
        assert y0 >= 0 and y1 <= 1000 and x0 >= 0 and x1 <= 1000


def test_window_smaller_than_min_when_image_is():
    bounds = np.array([[10.0, 10.0, 40.0, 40.0]])
    tiles = nc.assign_tiles(np.array([[25.0, 25.0]]), 300)
    wins = nc.tile_windows(bounds, tiles, 300, 8, 600, (400, 400))
    assert list(wins.values()) == [(0, 400, 0, 400)]


def test_cell_on_image_border_is_whole():
    image = np.zeros((1, 40, 40), dtype=np.float32)
    image[0, 5:15, 0:10] = 0.5
    geoms = [box(0, 5, 10, 15)]
    out = run(image, geoms, np.array([1]), {"c0": 1.0}, tile=16)
    # polygon() includes boundary pixels: the box covers 11x11 px, 100 of them 0.5 (50/121)
    assert out[0, 0] == pytest.approx(50 / 121)


def test_window_contains_neighbours():
    geoms = [box(10, 10, 20, 20), box(70, 10, 80, 20)]  # second owned by next tile
    labels = np.array([1, 2])
    tiles = nc.assign_tiles(np.array([[15.0, 15.0], [75.0, 15.0]]), 64)
    assert tiles.tolist() == [[0, 0], [1, 0]]
    bounds = np.array([g.bounds for g in geoms])
    wins = nc.tile_windows(bounds, tiles, 64, 16, 0, (200, 200))
    lab = nc.label_window(geoms, labels, wins[(0, 0)])
    assert lab.dtype == np.int32
    assert set(np.unique(lab)) == {0, 1, 2}


def test_every_window_gets_the_store_factor():
    rng = np.random.default_rng(1)
    image = rng.integers(0, 200, size=(1, 200, 200)).astype(np.float32)
    geoms, labels = grid_cells()
    seen = []

    def record(_ch, x, _lab):
        seen.append(x.copy())
        return x

    run(image, geoms, labels, {"c0": 100.0}, predict=record, tile=64)
    assert len(seen) > 1
    for x in seen:
        assert x.max() <= 1.0 and x.min() >= 0.0
        # recover the raw window by locating it: values are raw/100 clipped, so all lie on that grid
        raw = x * 100.0
        assert np.allclose(raw[x < 1.0], np.round(raw[x < 1.0]), atol=1e-3)
    full = np.clip(image[0] / 100.0, 0, 1)
    assert max(x.max() for x in seen) == pytest.approx(full.max())


def test_missing_factor_raises():
    image = np.ones((2, 100, 100), dtype=np.float32)
    geoms, labels = grid_cells(2)
    with pytest.raises(KeyError):
        run(image, geoms, labels, {"c0": 1.0})


def test_normalisation_deterministic_and_nonzero_only():
    rng = np.random.default_rng(2)
    img = rng.integers(0, 50, size=(1, 300, 300)).astype(np.float32)
    img[0, :150] = 0
    a = nc.normalisation_factors(img, ["c0"])
    b = nc.normalisation_factors(img, ["c0"])
    assert a == b
    nz = img[0][img[0] > 0]
    assert a["c0"] == pytest.approx(float(np.quantile(nz, nc.QUANTILE)))


def test_empty_channel_is_nan_column():
    rng = np.random.default_rng(3)
    image = np.stack([rng.integers(1, 9, size=(100, 100)), np.zeros((100, 100))]).astype(np.float32)
    factors = nc.normalisation_factors(image, ["c0", "c1"])
    assert factors["c1"] is None
    calls = []

    def predict(ch, x, _lab):
        calls.append(ch)
        return x

    geoms, labels = grid_cells(3)
    out = run(image, geoms, labels, factors, predict=predict)
    assert set(calls) == {"c0"}
    assert np.isnan(out[:, 1]).all() and np.isfinite(out[:, 0]).all()


def test_cell_without_pixel_centre_is_nan():
    image = np.ones((1, 50, 50), dtype=np.float32)
    geoms = [box(10, 10, 20, 20), box(30.1, 30.1, 30.3, 30.3)]
    out = run(image, geoms, np.array([1, 2]), {"c0": 1.0})
    assert out[0, 0] == pytest.approx(1.0) and np.isnan(out[1, 0])


def test_image_px_ceils():
    assert nc.image_px(2048, 0.65) == 3151


def box_blur(x, r):
    from scipy.ndimage import uniform_filter

    return uniform_filter(x, size=2 * r + 1, mode="nearest")


def test_margin_gives_whole_image_result_and_zero_margin_does_not():
    rng = np.random.default_rng(4)
    image = rng.integers(1, 100, size=(1, 200, 200)).astype(np.float32)
    # cells straddle tile edges at 64 and 100
    geoms, labels = grid_cells(8, step=24, size=12, x_off=3, y_off=3)
    factors = {"c0": 60.0}
    r = 6

    def blur(_ch, x, _lab):
        return box_blur(x, r)

    names = ["c0"]
    # a single window that holds everything is the whole-image reference
    ref = nc.score_cells(image, geoms, labels, names, factors, blur, 4096, 0, 0)
    for tile in (64, 100):
        tiled = nc.score_cells(image, geoms, labels, names, factors, blur, tile, r + 1, 0)
        np.testing.assert_allclose(tiled, ref, atol=1e-6)
        short = nc.score_cells(image, geoms, labels, names, factors, blur, tile, 0, 0)
        assert np.abs(short - ref).max() > 1e-4


def test_empty_and_none_geoms_are_skipped():
    image = np.ones((1, 60, 60), dtype=np.float32)
    geoms = [box(10, 10, 20, 20), None, Polygon(), box(30, 30, 40, 40)]
    out = run(image, geoms, np.array([1, 2, 3, 4]), {"c0": 1.0})
    assert out.shape == (4, 1)
    assert np.isnan(out[[1, 2], 0]).all()
    assert out[[0, 3], 0] == pytest.approx([1.0, 1.0])
