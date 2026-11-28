"""Model scale, window independence and slide statistics for VirTues."""

import json

import numpy as np
import pytest
from shapely.geometry import box

import virtues_stats as vs


def test_resample_identity_at_one_um():
    img = np.random.default_rng(0).integers(0, 1000, (1, 20, 30)).astype(np.uint16)
    out = vs.resample_window(img, 0, 0, 20, 0, 30, 1.0)
    assert out.dtype == np.float32 and np.array_equal(out, img[0].astype(np.float32))


def test_resample_area_average():
    img = np.arange(16, dtype=np.uint16).reshape(1, 4, 4)
    out = vs.resample_window(img, 0, 0, 2, 0, 2, 0.5)
    expected = img[0].astype(float).reshape(2, 2, 2, 2).mean(axis=(1, 3))
    assert vs.model_shape((4, 4), 0.5) == (2, 2)
    assert np.allclose(out, expected)


def test_resample_window_independent_bit_for_bit():
    rng = np.random.default_rng(1)
    img = rng.integers(0, 65535, (1, 300, 300)).astype(np.uint16)
    h, w = vs.model_shape((300, 300), 0.65)
    whole = vs.resample_window(img, 0, 0, h, 0, w, 0.65)
    for _ in range(20):
        y0, x0 = rng.integers(0, h - 1), rng.integers(0, w - 1)
        y1, x1 = rng.integers(y0 + 1, h + 1), rng.integers(x0 + 1, w + 1)
        assert np.array_equal(vs.resample_window(img, 0, y0, y1, x0, x1, 0.65), whole[y0:y1, x0:x1])


def test_resample_upsampling():
    img = np.arange(6, dtype=np.uint16).reshape(1, 2, 3)
    out = vs.resample_window(img, 0, 0, 4, 0, 6, 2.0)
    assert out.shape == (4, 6)
    assert np.array_equal(out, np.repeat(np.repeat(img[0], 2, axis=0), 2, axis=1).astype(np.float32))


def test_tissue_mask_pixel_centres():
    mask = vs.tissue_mask([box(0, 0, 10, 10)], 0, 40, 0, 40, 0.5)
    assert mask[:5, :5].all() and mask.sum() == 25


def make_hist(rng, scale):
    img = rng.integers(0, scale, (1, 64, 64)).astype(np.uint16)
    return img, vs.histogram(img, [box(0, 0, 64, 64)], [0], 1.0, rows=16)


def test_stats_equal_numpy():
    rng = np.random.default_rng(2)
    (a, ha), (b, hb) = make_hist(rng, 500), make_hist(rng, 3000)
    pooled = np.concatenate([a.ravel(), b.ravel()]).astype(np.float64)
    s = vs.stats_from_histogram(ha[0] + hb[0])
    cap = np.quantile(pooled, 0.99)
    x = np.log1p(np.minimum(pooled, cap))
    assert s["cap"] == cap and s["tissue_pixels"] == pooled.size
    assert np.isclose(s["mean"], x.mean(), rtol=1e-12) and np.isclose(s["sd"], x.std(), rtol=1e-12)


def test_histogram_only_tissue():
    rng = np.random.default_rng(3)
    img = rng.integers(0, 100, (1, 64, 64)).astype(np.uint16)
    poly = [box(0, 0, 32, 32)]
    base = vs.histogram(img, poly, [0], 1.0)
    img[:, 40:, 40:] = 9999
    assert np.array_equal(vs.histogram(img, poly, [0], 1.0), base)
    assert base.sum() == 32 * 32


def test_float_image_refused():
    with pytest.raises(TypeError, match="float32"):
        vs.histogram(np.zeros((1, 8, 8), dtype=np.float32), [box(0, 0, 8, 8)], [0], 1.0)


def test_constant_marker_refused():
    counts = np.zeros(vs.N_BINS, dtype=np.int64)
    counts[100] = 50
    with pytest.raises(ValueError, match="constant"):
        vs.stats_from_histogram(counts)


def test_no_tissue_refused():
    with pytest.raises(ValueError, match="no tissue"):
        vs.stats_from_histogram(np.zeros(vs.N_BINS, dtype=np.int64))


def write_hist(path, sample, markers, ids, seed=0):
    counts = np.zeros((len(markers), vs.N_BINS), dtype=np.int64)
    counts[:, :200] = np.random.default_rng(seed).integers(1, 20, (len(markers), 200))
    np.savez(path, counts=counts, markers=np.array(markers), uniprot_ids=np.array(ids), sample=sample)


def test_combine_writes_layout(tmp_path):
    write_hist(tmp_path / "a.npz", "A", ["CD3", "CD8"], ["P07766", "P01732"], 1)
    write_hist(tmp_path / "b.npz", "B", ["CD3", "CD8"], ["P07766", "P01732"], 2)
    out = tmp_path / "s.json"
    vs.combine([tmp_path / "a.npz", tmp_path / "b.npz"], "SL", 0.65, out)
    doc = json.loads(out.read_text())
    assert doc["format"] == 1 and doc["cores"] == ["A", "B"] and doc["pixel_size"] == 0.65
    assert set(doc["markers"]["CD3"]) == {"uniprot_id", "cap", "mean", "sd", "tissue_pixels"}
    assert vs.load_stats(out, [("CD3", "P07766")])["CD3"]["uniprot_id"] == "P07766"


def test_combine_refuses_mismatched_markers(tmp_path):
    write_hist(tmp_path / "a.npz", "A", ["CD3"], ["P07766"])
    write_hist(tmp_path / "b.npz", "B", ["CD3"], ["P99999"])
    with pytest.raises(ValueError, match="P99999"):
        vs.combine([tmp_path / "a.npz", tmp_path / "b.npz"], "SL", 1.0, tmp_path / "o.json")


def test_load_stats_id_mismatch(tmp_path):
    write_hist(tmp_path / "a.npz", "A", ["CD3"], ["P07766"])
    vs.combine([tmp_path / "a.npz"], "SL", 1.0, tmp_path / "s.json")
    with pytest.raises(ValueError, match="P11111"):
        vs.load_stats(tmp_path / "s.json", [("CD3", "P11111")])


def test_histogram_tiling_independent():
    rng = np.random.default_rng(4)
    img = rng.integers(0, 4000, (2, 150, 170)).astype(np.uint16)
    poly = [box(10, 5, 120, 140), box(130, 20, 165, 60)]
    assert np.array_equal(
        vs.histogram(img, poly, [0, 1], 0.65, rows=16), vs.histogram(img, poly, [0, 1], 0.65)
    )


WHOLE = box(0, 0, 40, 40)


def write_store(tmp_path, data, roi=WHOLE, roi_scale=1):
    """A real store; the ROI is kept 1/roi_scale in size with Scale(roi_scale), as sopa's tissue() does."""
    import geopandas as gpd
    import spatialdata as sd
    from shapely.affinity import scale
    from spatialdata.models import Image2DModel, ShapesModel
    from spatialdata.transformations import Scale

    shapes = {}
    if roi is not None:
        shapes[vs.TISSUE_KEY] = ShapesModel.parse(
            gpd.GeoDataFrame(geometry=[scale(roi, 1 / roi_scale, 1 / roi_scale, origin=(0, 0))]),
            transformations={"global": Scale([roi_scale, roi_scale], axes=("x", "y"))},
        )
    image = Image2DModel.parse(data, dims=("c", "y", "x"), c_coords=["CD3", "CD8"])
    sdata = sd.SpatialData(images={"img": image}, shapes=shapes)
    sdata.attrs["cell_segmentation_image"] = "img"
    path = tmp_path / "s.zarr"
    sdata.write(path)
    return path


def run_cli(tmp_path, dtype=np.uint16, shape=(2, 40, 40), pixel_size=1.0, **store):
    pytest.importorskip("spatialdata")
    data = np.random.default_rng(5).integers(0, 500, shape).astype(dtype)
    path = write_store(tmp_path, data, **store)
    out = tmp_path / "S1_virtues_hist.npz"
    argv = ["histogram", "--sdata", str(path), "--channels", "CD3:P07766,CD8:P01732"]
    return out, data, lambda: vs.main([*argv, "--pixel-size", str(pixel_size), "--output", str(out)])


def test_cli_histogram_writes_npz(tmp_path):
    out, _, run = run_cli(tmp_path)
    run()
    with np.load(out) as z:
        assert z["counts"].shape == (2, vs.N_BINS) and z["counts"].sum() == 2 * 40 * 40
        assert list(z["markers"]) == ["CD3", "CD8"] and list(z["uniprot_ids"]) == ["P07766", "P01732"]
        assert str(z["sample"]) == "S1"


def test_to_image_pixels_undoes_roi_scale():
    import geopandas as gpd
    from spatialdata.models import Image2DModel, ShapesModel
    from spatialdata.transformations import Scale

    image = Image2DModel.parse(np.zeros((1, 8, 8), np.uint16), dims=("c", "y", "x"))
    roi = ShapesModel.parse(
        gpd.GeoDataFrame(geometry=[box(4, 6, 14, 16)]),
        transformations={"global": Scale([16, 16], axes=("x", "y"))},
    )
    assert vs.to_image_pixels(roi, image)[0].equals(box(64, 96, 224, 256))


@pytest.mark.parametrize("pixel_size", [1.0, 0.65])
def test_cli_roi_on_coarse_level_counts_scale0_pixels(tmp_path, pixel_size):
    # sopa's tissue() keeps the ROI in its coarsest level's pixels, with a scale to global
    truth = box(64, 96, 224, 256)
    out, data, run = run_cli(tmp_path, shape=(2, 320, 320), pixel_size=pixel_size, roi=truth, roi_scale=16)
    run()
    with np.load(out) as z:
        counts = z["counts"]
    assert np.array_equal(counts, vs.histogram(data, [truth], [0, 1], pixel_size))
    if pixel_size == 1.0:
        assert counts.sum(axis=1).tolist() == [160 * 160] * 2


def test_cli_float_image_exits_naming_dtype(tmp_path):
    _, _, run = run_cli(tmp_path, dtype=np.float32)
    with pytest.raises(SystemExit) as e:
        run()
    assert "float32" in str(e.value)


def test_cli_missing_roi_counts_zero_tissue(tmp_path, capsys):
    # sopa writes no ROI when it finds no tissue, e.g. a nearly empty TMA core
    out, _, run = run_cli(tmp_path, roi=None)
    run()
    with np.load(out) as z:
        assert z["counts"].shape == (2, vs.N_BINS) and z["counts"].sum() == 0
    assert f"tissue segmentation found no tissue in {tmp_path / 's.zarr'}" in capsys.readouterr().err


def test_combine_slide_without_tissue_names_it(tmp_path):
    empty = np.zeros((1, vs.N_BINS), dtype=np.int64)
    np.savez(
        tmp_path / "a.npz",
        counts=empty,
        markers=np.array(["CD3"]),
        uniprot_ids=np.array(["P07766"]),
        sample="A",
    )
    args = ["combine", "--slide", "SL", "--pixel-size", "1.0", "--output", str(tmp_path / "s.json")]
    with pytest.raises(SystemExit) as e:
        vs.main([*args, str(tmp_path / "a.npz")])
    assert "tissue segmentation found no tissue on slide SL" in str(e.value)


def test_combine_constant_marker_names_remedy(tmp_path):
    counts = np.zeros((1, vs.N_BINS), dtype=np.int64)
    counts[0, 100] = 50
    np.savez(
        tmp_path / "a.npz",
        counts=counts,
        markers=np.array(["CD3"]),
        uniprot_ids=np.array(["P07766"]),
        sample="A",
    )
    with pytest.raises(ValueError, match="slide SL, marker CD3: .*constant.*uniprot_id.*virtues_stats"):
        vs.combine([tmp_path / "a.npz"], "SL", 1.0, tmp_path / "s.json")
