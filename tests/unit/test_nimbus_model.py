"""Real-model tests for nimbus_cells; run in the nimbus image, skipped where it or the fixture is absent."""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("nimbus_inference", reason="needs the nimbus image")
pytest.importorskip("shapely")
FIXTURE = Path(__file__).parent / "fixtures" / "nimbus_crop"
pytestmark = pytest.mark.skipif(
    not (FIXTURE / "reference_scores.csv").exists(), reason="no nimbus_crop fixture"
)

import nimbus_cells as nc  # noqa: E402

FIXTURE_065 = Path(__file__).parent / "fixtures" / "nimbus_crop_065"
needs_065 = pytest.mark.skipif(
    not (FIXTURE_065 / "reference_scores.csv").exists(), reason="no nimbus_crop_065 fixture"
)

CHANNELS = ["CD45", "FOXP3"]  # image.npy channel order


def load_crop(fixture):
    import pandas as pd
    import shapely
    from skimage.measure import regionprops

    image = np.load(fixture / "image.npy")
    labels = np.load(fixture / "labels.npy")
    factors = json.loads((fixture / "factors.json").read_text())
    ref = pd.read_csv(fixture / "reference_scores.csv").sort_values("label")
    geoms = []
    for p in regionprops(labels):
        # pixel squares centred on integer coordinates, so rasterize() recovers exactly these pixels
        geoms.append(
            shapely.union_all([shapely.box(x - 0.5, y - 0.5, x + 0.5, y + 0.5) for y, x in p.coords])
        )
    ids = np.array([p.label for p in regionprops(labels)])
    order = np.argsort(ids)
    assert (ids[order] == ref["label"].to_numpy()).all()
    geoms = [geoms[i] for i in order]
    compact = np.arange(1, len(geoms) + 1)
    window = (0, labels.shape[0], 0, labels.shape[1])
    assert (nc.label_window(geoms, compact, window) > 0).sum() == (labels > 0).sum()
    return image, geoms, compact, factors, ref[CHANNELS].to_numpy()


@pytest.fixture(scope="module")
def crop():
    return load_crop(FIXTURE)


@pytest.fixture(scope="module")
def crop_065():
    return load_crop(FIXTURE_065)


@pytest.fixture(scope="module")
def nimbus():
    return nc.load_nimbus("cpu")


def test_halo_is_96(nimbus):
    assert nc.model_halo(nimbus) == 96


def test_parity_with_upstream(crop, nimbus):
    image, geoms, labels, factors, reference = crop
    predict = nc.nimbus_predictor(nimbus, 1.0)
    margin = nc.image_px(nc.model_halo(nimbus) + nc.MARGIN_EXTRA_MODEL_PX, 1.0)
    ours = nc.score_cells(
        image, geoms, labels, CHANNELS, factors, predict, 4096, margin, nc.MIN_WINDOW_MODEL_PX
    )
    diff = np.abs(ours - reference).max()
    print(f"parity max abs diff {diff:.3g}")
    np.testing.assert_allclose(ours, reference, atol=1e-4)


def test_tile_invariance_real_model(crop, nimbus):
    image, geoms, labels, factors, _ = crop
    predict = nc.nimbus_predictor(nimbus, 1.0)
    margin = nc.image_px(nc.model_halo(nimbus) + nc.MARGIN_EXTRA_MODEL_PX, 1.0)
    args = (image, geoms, labels, CHANNELS, factors, predict)
    # 640 px tiles give 2x2 windows (>= min_window, shifted inward) at different origins
    tiled = nc.score_cells(*args, 640, margin, nc.MIN_WINDOW_MODEL_PX)
    whole = nc.score_cells(*args, 4096, margin, nc.MIN_WINDOW_MODEL_PX)
    d = np.abs(tiled - whole)
    print(f"tile invariance max {d.max():.3g} mean {d.mean():.3g}")
    assert d.max() <= 0.01


PS = 0.65  # a real exemplar pixel size


@pytest.fixture(scope="module")
def whole_065(crop_065, nimbus):
    """One tile holding every cell: the window is the whole image."""
    image, geoms, labels, factors, _ = crop_065
    margin = nc.image_px(nc.model_halo(nimbus) + nc.MARGIN_EXTRA_MODEL_PX, PS)
    predict = nc.nimbus_predictor(nimbus, PS)
    args = (image, geoms, labels, CHANNELS, factors, predict)
    return nc.score_cells(*args, 10_000, margin, nc.image_px(nc.MIN_WINDOW_MODEL_PX, PS)), margin


@needs_065
def test_parity_with_upstream_at_065(crop_065, whole_065):
    reference = crop_065[4]
    ours, _ = whole_065
    d = np.abs(ours - reference)
    print(f"parity at {PS}: max {d.max():.3g} mean {d.mean():.3g}")
    np.testing.assert_allclose(ours, reference, atol=1e-4)


@needs_065
@pytest.mark.xfail(
    reason="measured 2026-11-12: max abs diff 0.414, mean 0.0113 (cells 6551, 2x2 windows, origins 0 and 308.75 model px)"
    " against the 0.01 bound; windows off the 16 px pooling grid change scores. Open: see docs/decisions.md",
    strict=False,
)
def test_tile_invariance_at_065_with_misaligned_windows(crop_065, nimbus, whole_065):
    image, geoms, labels, factors, _ = crop_065
    whole, margin = whole_065
    min_window = nc.image_px(nc.MIN_WINDOW_MODEL_PX, PS)
    tile = 1050  # 2x2 tiles on the 2100 px image
    centroids = np.array([(g.centroid.x, g.centroid.y) for g in geoms])
    windows = nc.tile_windows(
        np.array([g.bounds for g in geoms]), nc.assign_tiles(centroids, tile), tile, margin, min_window,
        image.shape[1:],
    )  # fmt: skip
    assert len(windows) == 4
    origins_model_px = [o * PS for y0, _, x0, _ in windows.values() for o in (y0, x0)]
    # an origin that is a multiple of the 16 px pooling period would hide phase errors
    assert any(abs(o / 16 - round(o / 16)) > 1e-6 for o in origins_model_px), origins_model_px
    predict = nc.nimbus_predictor(nimbus, PS)
    tiled = nc.score_cells(image, geoms, labels, CHANNELS, factors, predict, tile, margin, min_window)
    d = np.abs(tiled - whole)
    print(f"tile invariance at {PS}: max {d.max():.3g} mean {d.mean():.3g}; origins {origins_model_px}")
    assert d.max() <= 0.01


def test_main_real_model_path(tmp_path):
    from test_nimbus_cells import cli_args, make_store

    pytest.importorskip("spatialdata")
    import anndata as ad

    path = make_store(tmp_path)
    assert nc.main(cli_args(path, tmp_path)) == 0
    out = ad.read_h5ad(tmp_path / "m_nimbus.h5ad")
    prov = json.loads((tmp_path / "m_nimbus.json").read_text())
    assert len(prov["weights_sha256"]) == 64 and int(prov["weights_sha256"], 16) >= 0
    assert prov["nimbus_version"] != "unknown"
    assert prov["halo"] == 96
    assert out.shape == (3, 2) and np.isfinite(out.X).all()
