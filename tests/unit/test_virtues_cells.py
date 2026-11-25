"""Tiled VirTues runner core, with a fake encoder: crops, windows, cells, niches."""

import json

import numpy as np
import pytest
from shapely.geometry import box

import virtues_cells as vc
import virtues_stats as vs

C = 3


# Copied from bunnelab/virtues d2c25e1, virtues/utils/cell_tokens.py (MIT), as the test reference.
def _get_uniform_crops(img, stride, tile_size=128):
    crops = []

    h, w = img.shape[-2:]
    indices_set = set()
    for i in range(0, h - tile_size + 1, stride):
        for j in range(0, w - tile_size + 1, stride):
            indices_set.add((i, j))

    last_i = h - tile_size
    for j in range(0, w - tile_size + 1, stride):
        indices_set.add((last_i, j))
    last_j = w - tile_size
    for i in range(0, h - tile_size + 1, stride):
        indices_set.add((i, last_j))
    indices_set.add((last_i, last_j))
    indices = sorted(list(indices_set))
    for i, j in indices:
        crop = img[:, i : i + tile_size, j : j + tile_size]
        crops.append(crop)
    for i in range(len(indices)):
        indices[i] = (indices[i][0], indices[i][1])
    return crops, indices


def fake_encode(crops):
    """Each patch's mean per channel, (n, 16, 16, c)."""
    n, c = crops.shape[:2]
    return crops.reshape(n, c, 16, 8, 16, 8).mean(axis=(3, 5)).transpose(0, 2, 3, 1).astype(np.float32)


def stats(mean=0.0, sd=1.0):
    return {"cap": np.full(C, 1e9), "mean": np.full(C, mean), "sd": np.full(C, sd)}


def make_image(h, w, seed=0):
    return np.random.default_rng(seed).integers(0, 2000, (C, h, w)).astype(np.uint16)


def reader(img, st, pixel_size=1.0):
    """read_input bound to an image, statistics and the padded shape."""
    h, w = vs.model_shape(img.shape[1:], pixel_size)
    padded = (h + 2 * vc.PAD, w + 2 * vc.PAD)

    def read_raw(c, y0, y1, x0, x1):
        return vs.resample_window(img, c, y0, y1, x0, x1, pixel_size)

    def read_input(y0, y1, x0, x1):
        return vc.model_input(read_raw, st, y0, y1, x0, x1, padded)

    return read_input, padded


def source(geoms, pixel_size=1.0):
    """CellSource in padded coordinates, from image-coordinate geoms."""
    centroids = np.array([(g.centroid.y, g.centroid.x) for g in geoms]) * pixel_size + vc.PAD
    b = np.array([g.bounds for g in geoms])  # minx, miny, maxx, maxy
    bboxes = b[:, [1, 3, 0, 2]] * pixel_size + vc.PAD
    return vc.CellSource(vc.label_reader(geoms, pixel_size), centroids, bboxes)


def edge_cells(h, w, n=40, seed=3):
    """Boxes straddling the tile-64 and tile-200 lines (in padded coordinates) and the image edge."""
    rng = np.random.default_rng(seed)
    lines = [t - vc.PAD for t in (128, 192, 200, 256, 320, 400) if t - vc.PAD > 0]
    geoms = []
    for k in range(n):
        size = rng.uniform(3, 25, 2)
        if k % 4 == 0:  # on the image edge
            y, x = rng.choice([0, h - size[0]]), rng.uniform(0, w - size[1])
        else:
            y = rng.choice(lines) - size[0] / 2 + rng.uniform(-2, 2)
            x = rng.choice(lines) - size[1] / 2 + rng.uniform(-2, 2)
        y, x = np.clip(y, 0, h - size[0]), np.clip(x, 0, w - size[1])
        geoms.append(box(x, y, x + size[1], y + size[0]))
    return geoms


def test_crop_grid_equals_upstream():
    for h, w in [(128, 128), (300, 517), (1000, 1000)]:
        _, expected = _get_uniform_crops(np.zeros((1, h, w)), vc.STEP, vc.CROP)
        assert vc.uniform_crops(h, w) == expected


def test_tiled_equals_whole_image_exactly():
    img = make_image(300, 260)
    read_input, padded = reader(img, stats(0.5, 2.0))
    sources = {"cells": source(edge_cells(300, 260))}
    runs = [vc.cell_embeddings(read_input, sources, padded, fake_encode, tile=t) for t in (64, 200, 4096)]
    emb, weight = runs[-1]["cells"]
    assert emb.dtype == np.float32 and weight.dtype == np.float64 and (weight > 0).sum() >= 35
    for run in runs[:-1]:
        assert np.array_equal(run["cells"][0], emb, equal_nan=True) and np.array_equal(
            run["cells"][1], weight
        )


def test_cell_matches_upstream_averaging():
    img = make_image(200, 180, seed=1)
    st = stats(0.5, 2.0)
    read_input, padded = reader(img, st)
    geoms = edge_cells(200, 180, n=25, seed=4)
    src = source(geoms)
    emb, weight = vc.cell_embeddings(read_input, {"cells": src}, padded, fake_encode, tile=128)["cells"]

    # port of upstream compute_cell_tokens on the whole padded image
    x = read_input(0, padded[0], 0, padded[1])
    mask = src.read_labels(0, padded[0], 0, padded[1])
    crops, indices = _get_uniform_crops(x, vc.STEP, vc.CROP)
    tokens = fake_encode(np.stack(crops))
    cell_tokens, weights = {}, {}
    for crop_token, (row, col) in zip(tokens, indices, strict=False):
        crop_mask = mask[row : row + vc.CROP, col : col + vc.CROP]
        for i in range(16):
            for j in range(16):
                patch = crop_mask[i * 8 : (i + 1) * 8, j * 8 : (j + 1) * 8]
                for cell_id, count in zip(*np.unique(patch, return_counts=True), strict=False):
                    if cell_id == 0:
                        continue
                    cell_tokens.setdefault(cell_id, []).append(crop_token[i, j])
                    weights.setdefault(cell_id, []).append(count)
    # cells hidden under earlier ones have no pixel, so upstream has no row for them
    assert sorted(cell_tokens) == list(np.flatnonzero(weight > 0) + 1) and len(cell_tokens) >= 20
    for cell_id, toks in cell_tokens.items():
        w = np.array(weights[cell_id], dtype=np.float32)
        expected = (np.stack(toks) * (w / w.sum())[:, None]).sum(axis=0)
        np.testing.assert_allclose(emb[cell_id - 1], expected, rtol=1e-6, atol=1e-6)


def test_two_methods_equal_one_at_a_time():
    img = make_image(260, 240, seed=2)
    read_input, padded = reader(img, stats())
    cells = edge_cells(260, 240, seed=5)
    nuclei = [g.buffer(-1.0) if g.area > 30 else g for g in cells[:30]]
    both = vc.cell_embeddings(
        read_input, {"cells": source(cells), "nuclei": source(nuclei)}, padded, fake_encode, tile=100
    )
    for name, geoms in [("cells", cells), ("nuclei", nuclei)]:
        alone = vc.cell_embeddings(read_input, {name: source(geoms)}, padded, fake_encode, tile=100)
        assert np.array_equal(both[name][0], alone[name][0], equal_nan=True)
        assert np.array_equal(both[name][1], alone[name][1])


def test_cell_without_pixel_is_nan():
    img = make_image(100, 100)
    read_input, padded = reader(img, stats())
    geoms = [box(20, 20, 30, 30), box(10.6, 40, 10.9, 60)]  # sliver between pixel centres 10.5 and 11.5
    emb, weight = vc.cell_embeddings(read_input, {"cells": source(geoms)}, padded, fake_encode)["cells"]
    assert weight[0] > 0 and weight[1] == 0
    assert np.isfinite(emb[0]).all() and np.isnan(emb[1]).all()


def test_overlap_earlier_cell_wins():
    geoms = [box(10, 10, 20, 20), box(15, 15, 25, 25)]
    read_labels = vc.label_reader(geoms, 1.0)
    p = vc.PAD
    whole = read_labels(p, p + 40, p, p + 40)
    assert whole.dtype == np.int32
    assert (whole[10:20, 10:20] == 1).all() and (whole == 2).sum() == 100 - 25
    # a window over the overlap alone gives the same labels
    assert np.array_equal(read_labels(p + 16, p + 22, p + 16, p + 22), whole[16:22, 16:22])
    img = make_image(60, 60)
    read_input, padded = reader(img, stats())
    _, weight = vc.cell_embeddings(read_input, {"cells": source(geoms)}, padded, fake_encode)["cells"]
    # a pixel in a crop overlap counts once per crop, so compare with an upstream-style count
    counts = np.zeros(3)
    labels = read_labels(0, padded[0], 0, padded[1])
    for i, j in vc.uniform_crops(*padded):
        counts += np.bincount(labels[i : i + 128, j : j + 128].ravel(), minlength=3)
    assert np.array_equal(weight, counts[1:])


def test_model_input_window_independent():
    img = make_image(150, 170, seed=6)
    st = stats(0.7, 1.5)
    read_input, (hp, wp) = reader(img, st, pixel_size=0.8)
    whole = read_input(0, hp, 0, wp)
    assert whole.dtype == np.float32 and whole.shape == (C, hp, wp)
    for y0, y1, x0, x1 in [
        (0, 40, 0, 50),
        (hp - 30, hp, wp - 60, wp),
        (vc.PAD - 2, vc.PAD + 3, vc.PAD - 1, vc.PAD + 9),
        (hp - vc.PAD - 3, hp - vc.PAD + 2, 50, 90),
        (130, 190, 140, 141),
    ]:
        assert np.array_equal(read_input(y0, y1, x0, x1), whole[:, y0:y1, x0:x1])
    # the pad is standardised zeros, blurred, as upstream pads before standardising
    assert np.allclose(whole[:, : vc.PAD - 1], -0.7 / 1.5)
    # the blur is torchvision's: 3 x 3 Gaussian, sigma 1, reflect border, on the padded image
    raw = np.zeros((C, hp, wp))
    h, w = hp - 2 * vc.PAD, wp - 2 * vc.PAD
    for c in range(C):
        raw[c, vc.PAD : vc.PAD + h, vc.PAD : vc.PAD + w] = vs.resample_window(img, c, 0, h, 0, w, 0.8)
    z = (np.log1p(raw) - 0.7) / 1.5
    k = np.exp(-0.5 * np.array([1.0, 0.0, 1.0]))
    k2 = np.outer(k, k) / k.sum() ** 2
    zp = np.pad(z, ((0, 0), (1, 1), (1, 1)), mode="reflect")
    blurred = sum(k2[a, b] * zp[:, a : a + hp, b : b + wp] for a in range(3) for b in range(3))
    np.testing.assert_allclose(whole, blurred, rtol=1e-5, atol=1e-5)


def niches(img, polygons, pixel_size=1.0):
    st = stats()
    read_input, _ = reader(img, st, pixel_size)
    shape = vs.model_shape(img.shape[1:], pixel_size)

    def read_tissue(y0, y1, x0, x1):
        return vs.tissue_mask(polygons, y0, y1, x0, x1, pixel_size)

    return read_input, vc.niche_embeddings(read_input, read_tissue, shape, fake_encode)


def test_niche_grid_and_threshold():
    img = make_image(300, 300)
    _, (origins, frac, emb) = niches(img, [box(0, 0, 300, 300)])
    assert origins == [(0, 0), (0, 128), (128, 0), (128, 128)]
    assert np.array_equal(frac, np.ones(4)) and emb.shape == (4, C) and emb.dtype == np.float32
    # 37 of 128 columns is 28.9% (dropped); 40 is 31.25% (kept)
    _, (origins, frac, _) = niches(img, [box(0, 0, 37, 128)])
    assert origins == []
    _, (origins, frac, _) = niches(img, [box(0, 0, 40, 128)])
    assert origins == [(0, 0)] and frac[0] == pytest.approx(40 / 128)


def test_niche_is_patch_mean():
    img = make_image(300, 300, seed=7)
    read_input, (origins, _, emb) = niches(img, [box(0, 0, 300, 300)])
    for (y, x), row in zip(origins, emb, strict=False):
        crop = read_input(y + vc.PAD, y + vc.PAD + 128, x + vc.PAD, x + vc.PAD + 128)
        np.testing.assert_allclose(row, fake_encode(crop[None]).reshape(256, C).mean(axis=0), rtol=1e-6)
        np.testing.assert_allclose(row, crop.mean(axis=(1, 2)), rtol=1e-5, atol=1e-6)


def test_tissue_is_mean_of_kept_niches():
    img = make_image(400, 300, seed=8)
    _, (origins, _, emb) = niches(img, [box(0, 0, 300, 150)])
    assert len(origins) == 2
    np.testing.assert_allclose(vc.tissue_embedding(emb), emb.mean(axis=0), rtol=1e-6)


def test_no_niche_gives_nan_tissue():
    img = make_image(300, 300)
    _, (origins, frac, emb) = niches(img, [])
    assert origins == [] and frac.shape == (0,) and emb.shape == (0, C)
    tissue = vc.tissue_embedding(emb)
    assert tissue.shape == (C,) and np.isnan(tissue).all()


# --- CLI, with a fake encoder ---

PANEL = [("CD45", "P08575"), ("CD3", "P07766"), ("PanCK", "P05787")]
FASTA = (
    ">sp|P08575|PTPRC_HUMAN Receptor-type tyrosine-protein phosphatase C\nMYLWLKLLAF\nGFAFLDTEVF\n"
    ">sp|P08575-8|PTPRC_HUMAN Isoform 8\nMYLWLK\n"
    ">sp|P07766|CD3E_HUMAN T-cell surface glycoprotein CD3 epsilon chain\nMQSGTHWRVL\n"
    ">sp|P05787|K2C8_HUMAN Keratin, type II cytoskeletal 8\nMSIRVTQKSY\nKVSTSGPRAF\n"
)


def fake_encode_512(crops):
    """fake_encode padded to the model's 512 columns."""
    tokens = fake_encode(crops)
    return np.pad(tokens, ((0, 0), (0, 0), (0, 0), (0, 512 - tokens.shape[-1])))


def write_stats(path, panel=PANEL):
    markers = {
        n: {"uniprot_id": u, "cap": 5000.0, "mean": 5.0, "sd": 1.5, "tissue_pixels": 100} for n, u in panel
    }
    path.write_text(json.dumps({"format": 1, "slide": "S", "markers": markers}))
    return path


def make_virtues_store(tmp_path, roi):
    """300 x 520 image px at 0.5 um/px (model 150 x 260): two methods, CD45 bright in cp_1 only."""
    import anndata as ad
    import geopandas as gpd
    import pandas as pd
    import spatialdata as sd
    from spatialdata.models import Image2DModel, ShapesModel, TableModel

    rng = np.random.default_rng(0)
    data = rng.integers(0, 200, (4, 300, 520)).astype(np.uint16)
    data[1, 100:150, 200:260] = 4000  # CD45 inside cp_1
    image = Image2DModel.parse(
        data, dims=("c", "y", "x"), c_coords=["DNA", "CD45", "CD3", "PanCK"], scale_factors=[2]
    )
    cells = {
        "cellpose": {
            "cp_0": box(10, 10, 40, 40),
            "cp_1": box(200, 100, 260, 150),
            "cp_2": box(400, 200, 460, 260),
            "cp_3": box(100.2, 100, 100.4, 140),  # between pixel centres at 0.5 um/px: no pixel
        },
        "stardist": {"sd_0": box(15, 15, 35, 35), "sd_1": box(210, 110, 250, 140)},
    }
    shapes, tables = {}, {}
    for m, geoms in cells.items():
        ids = list(geoms)[::-1]  # table order differs from the shapes'
        shapes[f"{m}_cells"] = ShapesModel.parse(
            gpd.GeoDataFrame(geometry=list(geoms.values()), index=pd.Index(list(geoms)))
        )
        obs = pd.DataFrame(
            {
                "region": pd.Categorical([f"{m}_cells"] * len(ids)),
                "slide": pd.Categorical(["S"] * len(ids)),
                "core_id": pd.Categorical(["A1"] * len(ids)),
                "cell_id": ids,
            },
            index=ids,
        )
        tables[f"{m}_table"] = TableModel.parse(
            ad.AnnData(np.zeros((len(ids), 1), dtype=np.float32), obs=obs, var=pd.DataFrame(index=["x"])),
            region=f"{m}_cells",
            region_key="region",
            instance_key="cell_id",
        )
    shapes["region_of_interest"] = ShapesModel.parse(gpd.GeoDataFrame(geometry=[roi]))
    sdata = sd.SpatialData(images={"img": image}, shapes=shapes, tables=tables)
    sdata.attrs["cell_segmentation_image"] = "img"
    path = tmp_path / "s.zarr"
    sdata.write(path)
    return path


def run_cli(tmp_path, monkeypatch, roi, panel=PANEL, stats_panel=PANEL, device="cuda"):
    pytest.importorskip("spatialdata")
    fasta = tmp_path / "uniprot.fasta"
    fasta.write_text(FASTA)
    monkeypatch.setenv("VIRTUES_UNIPROT", str(fasta))
    path = make_virtues_store(tmp_path, roi)
    out = tmp_path / "out"
    argv = [
        "--sdata", str(path), "--methods", "cellpose,stardist",
        "--channels", ",".join(f"{n}:{u}" for n, u in panel), "--unembedded", "DNA",
        "--stats", str(write_stats(tmp_path / "S_virtues_stats.json", stats_panel)),
        "--pixel-size", "0.5", "--device", device, "--outdir", str(out),
    ]  # fmt: skip
    return vc.main(argv, encode=fake_encode_512), out


UNS_KEYS = {
    "virtues_commit", "weights", "weights_sha256", "esm_model", "uniprot_release", "channels",
    "unembedded", "stats", "pixel_size", "model_um_per_px", "crop_size", "crop_step", "patch_size",
    "padding", "tile_size", "batch_size", "device", "n_cells", "n_cells_without_pixel",
    "n_niches_kept", "n_niches_dropped",
}  # fmt: skip


def test_cli_outputs_layout(tmp_path, monkeypatch):
    rc, out = run_cli(tmp_path, monkeypatch, roi=box(0, 0, 260, 300))  # left half: square 0 only
    assert rc == 0
    import anndata as ad
    import geopandas as gpd

    names = [f"virtues_{i}" for i in range(512)]
    cp = ad.read_h5ad(out / "cellpose_virtues.h5ad")
    assert list(cp.obs_names) == ["cp_3", "cp_2", "cp_1", "cp_0"]
    assert cp.X.dtype == np.float16 and list(cp.var_names) == names
    assert {"region", "slide", "core_id", "cell_id"} <= set(cp.obs.columns)
    assert set(cp.obs["region"]) == {"cellpose_cells"}
    assert cp.uns["spatialdata_attrs"]["instance_key"] == "cell_id"
    x = np.asarray(cp.X, dtype=np.float32)
    assert np.isnan(x[0]).all() and np.isfinite(x[1:]).all()
    # CD45 (column 0) is bright only in cp_1: a misaligned shape/table join breaks this
    assert x[2, 0] > x[1, 0] + 1 and x[2, 0] > x[3, 0] + 1
    sdist = ad.read_h5ad(out / "stardist_virtues.h5ad")
    assert list(sdist.obs_names) == ["sd_1", "sd_0"] and np.isfinite(np.asarray(sdist.X, np.float32)).all()

    uns = cp.uns["virtues"]
    assert set(uns) == UNS_KEYS
    assert dict(uns["channels"]) == dict(PANEL) and list(uns["unembedded"]) == ["DNA"]
    assert dict(uns["n_cells"]) == {"cellpose": 4, "stardist": 2}
    assert dict(uns["n_cells_without_pixel"]) == {"cellpose": 1, "stardist": 0}
    assert uns["n_niches_kept"] == 1 and uns["n_niches_dropped"] == 1
    assert uns["pixel_size"] == 0.5 and uns["batch_size"] == vc.BATCH and uns["device"] == "cuda"
    assert set(json.loads((out / "virtues.json").read_text())) == UNS_KEYS

    niches = gpd.read_parquet(out / "virtues_niches.parquet")
    assert list(niches.index) == ["niche_0"]
    assert niches.geometry.iloc[0].equals(box(0, 0, 256, 256))  # model 128 px at 0.5 um/px
    nt = ad.read_h5ad(out / "virtues_niches_table.h5ad")
    assert list(nt.obs_names) == ["niche_0"] and list(nt.obs["niche_id"]) == ["niche_0"]
    assert nt.obs["tissue_fraction"].iloc[0] == 1.0
    assert nt.obs["slide"].iloc[0] == "S" and nt.obs["core_id"].iloc[0] == "A1"
    assert nt.X.dtype == np.float16 and nt.X.shape == (1, 512)
    assert nt.uns["spatialdata_attrs"]["region"] == "virtues_niches"
    assert nt.uns["spatialdata_attrs"]["instance_key"] == "niche_id"
    assert set(nt.uns["virtues"]) == UNS_KEYS

    tissue = ad.read_h5ad(out / "virtues_tissue.h5ad")
    assert tissue.n_obs == 1 and tissue.X.dtype == np.float16
    assert tissue.obs["slide"].iloc[0] == "S" and tissue.obs["core_id"].iloc[0] == "A1"
    assert tissue.obs["n_niches"].iloc[0] == 1
    assert np.array_equal(tissue.X, nt.X)
    assert set(tissue.uns["virtues"]) == UNS_KEYS


def test_cli_no_niche_writes_no_niche_files(tmp_path, monkeypatch):
    rc, out = run_cli(tmp_path, monkeypatch, roi=box(0, 0, 20, 20))
    assert rc == 0
    import anndata as ad

    assert not (out / "virtues_niches.parquet").exists()
    assert not (out / "virtues_niches_table.h5ad").exists()
    tissue = ad.read_h5ad(out / "virtues_tissue.h5ad")
    assert tissue.X.shape == (1, 512) and np.isnan(np.asarray(tissue.X, np.float32)).all()
    assert tissue.obs["n_niches"].iloc[0] == 0
    uns = tissue.uns["virtues"]
    assert uns["n_niches_kept"] == 0 and uns["n_niches_dropped"] == 2
    assert (out / "cellpose_virtues.h5ad").exists()


def test_unknown_uniprot_id_exits_naming_it(tmp_path, monkeypatch, capsys):
    panel = [*PANEL[:2], ("PanCK", "Q99999")]
    with pytest.raises(SystemExit) as e:
        run_cli(tmp_path, monkeypatch, roi=box(0, 0, 260, 300), panel=panel, stats_panel=panel)
    assert e.value.code == 1 and "Q99999" in capsys.readouterr().err


def test_stats_mismatch_exits(tmp_path, monkeypatch, capsys):
    stats_panel = [*PANEL[:2], ("PanCK", "P08575-8")]
    with pytest.raises(SystemExit) as e:
        run_cli(tmp_path, monkeypatch, roi=box(0, 0, 260, 300), stats_panel=stats_panel)
    err = capsys.readouterr().err
    assert e.value.code == 1 and "PanCK" in err and "P08575-8" in err


def test_unknown_channel_exits_naming_it(tmp_path, monkeypatch, capsys):
    panel = [*PANEL, ("NOPE", "P08575")]
    with pytest.raises(SystemExit) as e:
        run_cli(tmp_path, monkeypatch, roi=box(0, 0, 260, 300), panel=panel, stats_panel=panel)
    err = capsys.readouterr().err
    assert e.value.code == 1 and "NOPE" in err and "DNA" in err


def test_non_cuda_device_exits(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        run_cli(tmp_path, monkeypatch, roi=box(0, 0, 260, 300), device="cpu")
    assert e.value.code == 1 and "cpu" in capsys.readouterr().err


def test_uniprot_sequences(tmp_path):
    fasta = tmp_path / "u.fasta"
    fasta.write_text(FASTA)
    seqs = vc.uniprot_sequences(fasta, ["P05787", "P08575-8", "P08575"])
    assert seqs == {"P05787": "MSIRVTQKSYKVSTSGPRAF", "P08575-8": "MYLWLK", "P08575": "MYLWLKLLAFGFAFLDTEVF"}
    with pytest.raises(KeyError, match="Q99999"):
        vc.uniprot_sequences(fasta, ["P05787", "Q99999"])


def test_cell_source_clips_to_model_grid():
    # 1003 image px at 0.65 um/px is 651 model px; model row 651's centre (image y 1002.3) is in the image
    h = vs.model_shape((1003, 40), 0.65)
    src = vc.cell_source([box(0, 990, 20, 1003), box(0, 1010, 20, 1020)], 0.65, h)
    labels = src.read_labels(vc.PAD + 640, vc.PAD + 660, vc.PAD, vc.PAD + 20)
    assert (labels[: 651 - 640] == 1).any() and not labels[651 - 640 :].any()
    assert src.bboxes[0, 1] == vc.PAD + 651 and (src.bboxes[1] == 0).all()
