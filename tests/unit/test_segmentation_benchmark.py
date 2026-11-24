"""Unit tests for the segmentation benchmark tools."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from segmentation_benchmark import settings
from segmentation_benchmark.scoring import score
from segmentation_benchmark.settings import TODAY, build_settings, today_index


def square(labels, value, y, x, size=10):
    labels[y : y + size, x : x + size] = value


def test_identical_masks_score_one():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0)
    square(t, 2, 20, 20)
    s = score(t, t.copy())
    assert (s["tp"], s["fp"], s["fn"], s["f1"], s["mean_ap"]) == (2, 0, 0, 1.0, 1.0)


def test_shifted_object_counts_by_iou():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0)
    p = np.zeros_like(t)
    square(p, 7, 0, 2)  # IoU 80/120 = 0.667, labels need not match
    s = score(t, p)
    assert s["tp"] == 1 and s["ap_60"] == 1.0 and s["ap_70"] == 0.0


def test_one_side_empty_is_zero_both_empty_is_nan():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0)
    assert score(t, np.zeros_like(t))["f1"] == 0.0
    assert np.isnan(score(np.zeros_like(t), np.zeros_like(t))["f1"])


def test_split_cell_is_one_fn_three_fp():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0, 20)  # 400 px
    p = np.zeros_like(t)
    p[0:20, 0:7] = 1
    p[0:20, 7:14] = 2
    p[0:20, 14:20] = 3  # IoU 0.35, 0.35, 0.30
    s = score(t, p)
    assert (s["tp"], s["fp"], s["fn"]) == (0, 3, 1)


def test_exact_half_iou_matches_once():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0, 20)  # 400 px
    p = np.zeros_like(t)
    p[0:20, 0:10] = 1
    p[0:20, 10:20] = 2  # each IoU exactly 0.5
    s = score(t, p)
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 0)


def test_layout():
    s = build_settings()
    assert len(s) == 168 and list(s["index"]) == list(range(168))
    assert (s[:144]["scope"] == "raw").all() and (s[144:156]["scope"] == "tissuenet").all()
    assert (s[156:]["target"] == "nuclei").all() and (s[156:]["scope"] == "all").all()


def test_today_is_in_every_block():
    s = build_settings()
    for target, scope in [("cells", "raw"), ("cells", "tissuenet"), ("nuclei", "all")]:
        row = s.loc[today_index(s, target, scope)]
        assert (row["gaussian_sigma"], row["clip_limit"], row["flow_threshold"]) == (1, 0.2, 2)


def test_today_index_raises_when_absent():
    s = build_settings()
    s = s[s["clip_limit"] != TODAY["clip_limit"]]
    with pytest.raises(ValueError, match="cells.*raw"):
        today_index(s, "cells", "raw")


def test_committed_csv_matches():
    committed = pd.read_csv(Path(settings.__file__).with_name("settings.csv"))
    pd.testing.assert_frame_equal(committed, build_settings(), check_dtype=False)


# Preprocessing ----------------------------------------------------------------------------

NAMES = ["DNA_1", "CD45", "ECAD", "FLAT"]


def raw_image():
    rng = np.random.default_rng(0)
    data = rng.integers(0, 1000, size=(4, 64, 64), dtype=np.uint16)
    data[3] = 5  # constant channel
    return data


@pytest.mark.parametrize("method", ["max", "mean"])
@pytest.mark.parametrize("sigma", [0, 1])
def test_project_matches_pipeline(tmp_path, monkeypatch, method, sigma):
    import project_channels
    import spatialdata as sd
    from segmentation_benchmark.preprocess import project
    from spatialdata.models import Image2DModel

    data = raw_image()
    # One level, one chunk, no tissue shapes: the pipeline's percentiles come from the full image.
    image = Image2DModel.parse(data, dims=("c", "y", "x"), c_coords=NAMES, chunks=(1, 64, 64))
    path = tmp_path / "sample.zarr"
    sd.SpatialData(images={"sample": image}).write(path)
    rows = ["channel_number,cycle_number,marker_name,channel_role,segmentation", "1,1,DNA_1,dna,nuclear"]
    rows += [f"{i},1,{n},marker,cell" for i, n in enumerate(NAMES[1:], start=2)]
    sheet = tmp_path / "markers.csv"
    sheet.write_text("\n".join(rows) + "\n")

    monkeypatch.chdir(tmp_path)
    project_channels.project(path, sheet, method=method, low=1, high=99.9, sigma=sigma, prefix="s")
    out = sd.read_zarr(path)["sample_projected"]
    level = next(iter(out.values())) if hasattr(out, "children") else out
    expected = np.asarray(level.sel(c=["cell", "nuclear"]).data)

    np.testing.assert_array_equal(project(data, 0, method, 1, sigma), expected)


def test_flat_marker_left_out_all_flat_gives_zeros():
    from segmentation_benchmark.preprocess import project

    data = raw_image()
    with_flat = project(data, 0, "max", 1, 1)
    without = project(data[:3], 0, "max", 1, 1)
    np.testing.assert_array_equal(with_flat, without)

    all_flat = np.stack([data[0], data[3], data[3]])
    out = project(all_flat, 0, "max", 1, 1)
    assert out.shape == (2, 64, 64) and out.dtype == np.uint16
    assert not out[0].any() and out[1].any()


def test_pad_round_trip():
    from segmentation_benchmark.preprocess import pad_to, unpad

    image = np.random.default_rng(0).random((2, 100, 100)).astype(np.float32)
    padded, shape = pad_to(image)
    assert padded.shape == (2, 256, 256) and shape == (100, 100)
    np.testing.assert_array_equal(padded[:, :100, :100], image)

    big = np.zeros((2, 300, 40), np.float32)
    assert pad_to(big)[0].shape == (2, 300, 256)

    labels = np.zeros((256, 256), int)
    labels[10:20, 10:20] = 7
    labels[50:60, 50:60] = 9
    labels[200:210, 200:210] = 11  # in the padding, cropped away
    out = unpad(labels, shape)
    assert out.shape == (100, 100)
    assert sorted(np.unique(out)) == [0, 1, 2]


def _square_roi(y, x, size=10):
    import roifile

    pts = np.array([[x, y], [x + size, y], [x + size, y + size], [x, y + size]])
    return roifile.ImagejRoi.frompoints(pts)


def test_polygon_rois_rasterise():
    from segmentation_benchmark.prepare import rois_to_labels

    labels, overlap = rois_to_labels([_square_roi(0, 0), _square_roi(30, 30)], (50, 50))
    assert sorted(np.unique(labels)) == [0, 1, 2]
    assert (labels == 1).sum() == (labels == 2).sum() > 50
    assert overlap == 0


def test_overlap_goes_to_later_roi_and_is_reported():
    from segmentation_benchmark.prepare import rois_to_labels

    labels, overlap = rois_to_labels([_square_roi(0, 0), _square_roi(5, 5)], (50, 50))
    assert overlap > 0
    assert labels[7, 7] == 2


def test_unsupported_roi_names_type():
    import roifile
    from segmentation_benchmark.prepare import rois_to_labels

    roi = _square_roi(0, 0)
    roi.roitype = roifile.ROI_TYPE.OVAL
    with pytest.raises(ValueError, match="OVAL"):
        rois_to_labels([roi], (50, 50))


def test_tonsil_dna_is_brightest_in_nuclei():
    from segmentation_benchmark.prepare import tonsil_nuclear_channel

    rng = np.random.default_rng(0)
    image = rng.random((3, 40, 40)) + 5  # channel 0 is brighter overall, but flat
    image[0] += 10
    nuclei = np.zeros((40, 40), int)
    nuclei[10:20, 10:20] = 1
    image[2][nuclei > 0] += 20
    assert tonsil_nuclear_channel(image, nuclei) == 2


def test_dapi_from_composite_ignores_cyan():
    from segmentation_benchmark.prepare import dapi_from_composite

    rng = np.random.default_rng(0)
    image = rng.random((3, 40, 40)).astype(np.float32)
    rgb = np.zeros((40, 40, 3))
    rgb[..., 2] = image[1] + image[2]  # channel 1 is blue, channel 2 is cyan (G and B)
    rgb[..., 1] = image[2]
    assert dapi_from_composite(image, rgb) == (1, "")


def test_tissuenet_meta_maps_one_to_one_after_headers(tmp_path):
    from segmentation_benchmark.prepare import read_tissuenet

    header = ["filename", "experiment", "pixel_size", "screening_passed", "time_step", "specimen"]
    meta = np.array(
        [header] * 4 + [["f", "../x/20200101_CyCIF_Tonsil", 0.5, "Not screened", None, "Tonsil"]] * 2,
        dtype=object,
    )
    x = np.zeros((2, 8, 8, 2))
    x[1, ..., 1] = 3.0
    y = np.zeros((2, 8, 8, 2), np.int32)
    y[0, :4, :4, 0] = 1
    y[0, :2, :2, 1] = 1
    path = tmp_path / "t.npz"
    np.savez(path, X=x, y=y, meta=meta)
    (row0, img0, cells0, nuclei0), (row1, img1, _, _) = list(read_tissuenet(path))
    assert (row0["crop"], row0["platform"], row0["tissue"], row0["nuclear"]) == (
        "0000",
        "20200101_CyCIF_Tonsil",
        "Tonsil",
        0,
    )
    assert img0.shape == (2, 8, 8) and img1[1].max() == 3.0 and img1[0].max() == 0
    assert (cells0 > 0).sum() == 16 and (nuclei0 > 0).sum() == 4

    np.savez(path, X=x, y=y, meta=meta[:-1])
    with pytest.raises(ValueError, match="tiles"):
        list(read_tissuenet(path))


# --- run.py ---------------------------------------------------------------------------------


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """Tiny data dir (one crop per dataset, cells+nuclei masks) and run.segment returning truth."""
    import tifffile
    from segmentation_benchmark import run

    data = tmp_path / "data"
    rows = []
    for dataset, nch in [("crossplatform", 3), ("tonsil", 3), ("tissuenet", 2)]:
        d = data / "crops" / dataset / "c1"
        d.mkdir(parents=True)
        rng = np.random.default_rng(0)
        tifffile.imwrite(d / "image.tif", rng.integers(0, 1000, (nch, 40, 40)).astype(np.uint16))
        lab = np.zeros((40, 40), np.uint32)
        square(lab, 1, 2, 2)
        square(lab, 2, 20, 20)
        tifffile.imwrite(d / "cells.tif", lab)
        tifffile.imwrite(d / "nuclei.tif", lab)
        rows.append((dataset, "c1", "p", "t", 0.5, "a|b|c", 0, 40, 40, True, 2, 2))
    cols = "dataset crop platform tissue pixel_size_um channels nuclear height width montage n_cells n_nuclei"
    pd.DataFrame(rows, columns=cols.split()).to_csv(data / "crops.csv", index=False)

    calls = []

    def fake(image, channels, _setting, _gpu):
        calls.append(channels)
        return tifffile.imread(data / "crops" / "tonsil" / "c1" / "cells.tif")[
            : image.shape[1], : image.shape[2]
        ]

    monkeypatch.setattr(run, "segment", fake)
    return run, data, tmp_path / "out", calls


def test_skips_existing_result(bench):
    run, data, out, calls = bench
    (out / "results").mkdir(parents=True)
    (out / "results" / "3.csv").write_text("x\n")
    run.run(data, 3, out)
    assert calls == []


def test_overwrites_stale_tmp_and_writes_atomically(bench):
    run, data, out, _ = bench
    (out / "results").mkdir(parents=True)
    (out / "results" / "3.csv.tmp").write_text("stale")
    run.run(data, 3, out)  # cells, raw: crossplatform + tonsil
    df = pd.read_csv(out / "results" / "3.csv")
    assert len(df) == 2 and (df["f1"] == 1.0).all()
    assert not (out / "results" / "3.csv.tmp").exists()
    assert (out / "labels" / "3" / "tonsil__c1.tif").exists()


def test_scope_selects_crops(bench):
    run, data, out, _ = bench
    run.run(data, 150, out)  # cells, tissuenet
    assert set(pd.read_csv(out / "results" / "150.csv")["dataset"]) == {"tissuenet"}
    run.run(data, 160, out)  # nuclei, all
    assert set(pd.read_csv(out / "results" / "160.csv")["dataset"]) == {
        "crossplatform",
        "tonsil",
        "tissuenet",
    }
    run.run(data, 3, out)
    assert "tissuenet" not in set(pd.read_csv(out / "results" / "3.csv")["dataset"])


def test_partial_run_is_kept_out_of_results(bench):
    run, data, out, _ = bench
    run.run(data, 3, out, limit_crops=1)
    assert not (out / "results" / "3.csv").exists()
    assert len(pd.read_csv(out / "results" / "3.partial.csv")) == 1
    run.run(data, 3, out)  # the full run still happens
    assert len(pd.read_csv(out / "results" / "3.csv")) == 2


def test_no_crops_is_an_error(bench):
    run, data, out, _ = bench
    with pytest.raises(SystemExit, match="setting 3"):
        run.run(data, 3, out, dataset="tissuenet")
    assert not (out / "results" / "3.csv").exists()


def fake_results(tmp_path, f1_by_setting):
    """results/<N>.csv from {index: {dataset: [f1, ...]}}; returns (results, data, out) dirs."""
    results = tmp_path / "out" / "results"
    results.mkdir(parents=True)
    for index, by_dataset in f1_by_setting.items():
        rows = [
            {
                "index": index,
                "target": "cells",
                "dataset": dataset,
                "crop": f"c{i}",
                "platform": "Vectra",
                "n_true": 5,
                "n_pred": 5,
                "f1": f1,
                "mean_ap": f1 / 2,
                "seconds": 1.0,
            }
            for dataset, values in by_dataset.items()
            for i, f1 in enumerate(values)
        ]
        pd.DataFrame(rows).to_csv(results / f"{index}.csv", index=False)
    data = tmp_path / "data"
    data.mkdir()
    (data / "crops.csv").write_text("dataset,crop,platform,nuclear,montage\n")
    return results, data, tmp_path / "report"


def test_summary_ranks_by_crossplatform_f1(tmp_path):
    import json

    from segmentation_benchmark import report

    results, data, out = fake_results(
        tmp_path,
        {
            0: {"crossplatform": [0.5, 0.5], "tissuenet": [0.9]},
            1: {"crossplatform": [0.6, 0.6], "tissuenet": [0.8]},
            2: {"crossplatform": [0.9, 0.9], "tissuenet": [0.1]},
        },
    )
    report.build_report(results, data, out)
    headline = json.loads((out / "headline.json").read_text())
    assert headline["cells_raw"]["best"]["index"] == 2
    assert headline["cells_raw"]["best"]["f1_by_dataset"]["tissuenet"] == pytest.approx(0.1)


def test_nan_crops_are_counted_and_excluded(tmp_path):
    from segmentation_benchmark import report

    results, data, out = fake_results(tmp_path, {0: {"crossplatform": [0.8, float("nan"), 0.6]}})
    report.build_report(results, data, out)
    row = pd.read_csv(out / "summary.csv").query("`index` == 0 and dataset == 'crossplatform'").iloc[0]
    assert (row["n_crops"], row["n_nan"]) == (3, 1)
    assert row["mean_f1"] == pytest.approx(0.7)


def test_partial_results_are_ignored(tmp_path):
    from segmentation_benchmark import report

    results, data, out = fake_results(tmp_path, {0: {"crossplatform": [0.8]}})
    (results / "1.partial.csv").write_text("garbage")
    report.build_report(results, data, out)
    assert set(pd.read_csv(out / "summary.csv")["index"]) == {0}


def test_missing_setting_is_listed_and_flagged(tmp_path):
    import json

    from segmentation_benchmark import report

    results, data, out = fake_results(
        tmp_path, {i: {"crossplatform": [0.5 + i / 100]} for i in (0, 2, 18)}
    )  # setting 1 is absent; 18 is today
    report.build_report(results, data, out)
    head = json.loads((out / "headline.json").read_text())
    assert 1 in head["missing_settings"] and 0 not in head["missing_settings"]
    assert 1 in head["cells_raw"]["missing_settings"] and head["cells_raw"]["today_missing"] is False
    assert (out / "effects_clip_limit.png").exists()


def test_missing_today_is_flagged(tmp_path):
    import json

    from segmentation_benchmark import report

    results, data, out = fake_results(tmp_path, {0: {"crossplatform": [0.5]}, 1: {"crossplatform": [0.6]}})
    report.build_report(results, data, out)
    head = json.loads((out / "headline.json").read_text())
    assert head["cells_raw"]["today_missing"] is True and head["cells_raw"]["today"] is None


def test_vectra_dapi_methods_disagree_skips_crop(tmp_path):
    from PIL import Image
    from segmentation_benchmark.prepare import _vectra_nuclear

    rng = np.random.default_rng(0)
    img = rng.random((3, 40, 40)).astype(np.float32)
    rgb = np.zeros((40, 40, 3), np.uint8)
    rgb[..., 2] = (img[1] * 255).astype(np.uint8)  # composite says channel 1
    Image.fromarray(rgb).save(tmp_path / "x-Crop_Cell_Png.png")
    dapi = (img[2] * 255).astype(np.uint8)  # DAPI render says channel 2
    Image.fromarray(dapi).save(tmp_path / "x-Crop_Dapi_Png.png")
    skipped = []
    assert _vectra_nuclear(img, tmp_path, skipped) == (None, "disagree")
    assert "ch1" in skipped[0][1] and "ch2" in skipped[0][1]

    Image.fromarray((img[1] * 255).astype(np.uint8)).save(tmp_path / "x-Crop_Dapi_Png.png")
    assert _vectra_nuclear(img, tmp_path, []) == (1, "agree")


def _imagej_tif(path, info):
    import tifffile

    tifffile.imwrite(
        path, np.zeros((3, 8, 8), np.float32), imagej=True, metadata={"axes": "CYX", "Info": info}
    )


def test_vectra_channel_names_from_imagej_info(tmp_path):
    from segmentation_benchmark.prepare import vectra_channel_names

    _imagej_tif(
        tmp_path / "a.tif",
        "Foo = 1\nName #1 = CD8 (Opal 650)\nName #2 = Hoechst (DAPI)\nName #3 = Autofluorescence\n",
    )
    assert vectra_channel_names(tmp_path / "a.tif") == [
        "CD8 (Opal 650)",
        "Hoechst (DAPI)",
        "Autofluorescence",
    ]
    _imagej_tif(tmp_path / "b.tif", "Name #1 = CD8\nName #3 = DAPI\n")  # gap: not trusted
    assert vectra_channel_names(tmp_path / "b.tif") is None
    _imagej_tif(tmp_path / "c.tif", "no names here")
    assert vectra_channel_names(tmp_path / "c.tif") is None


def test_is_dna_name():
    from segmentation_benchmark.prepare import is_dna_name

    assert is_dna_name("DAPI") and is_dna_name("Hoechst (DAPI)") and is_dna_name("DAPI1")
    assert not is_dna_name("CD8 (Opal 650)") and not is_dna_name("Autofluorescence")


P01 = "GITR (Opal 520)|IDO (Opal 570)|Ki67 (Opal 540)|Foxp3 (Opal 620)|CD8 (Opal 650)|DAPI|panCK (Opal 690)|Autofluorescence"


@pytest.mark.parametrize(
    ("selection", "expected"),
    [("all", [0, 1, 2, 3, 4, 6, 7]), ("markers", [0, 1, 2, 3, 4, 6]), ("membrane", [0, 1, 4, 6])],
)
def test_cell_channel_selection(selection, expected):
    from segmentation_benchmark.preprocess import cell_channels

    assert cell_channels(P01.split("|"), 5, selection) == expected


def test_cell_channel_selection_rejects_unknown_and_empty():
    from segmentation_benchmark.preprocess import cell_channels

    with pytest.raises(ValueError, match="selection"):
        cell_channels(["CD8", "DAPI"], 1, "nope")
    with pytest.raises(ValueError, match="no cell channels"):
        cell_channels(["Ki67", "DAPI", "Autofluorescence"], 1, "membrane")


def test_project_uses_only_selected_channels():
    from segmentation_benchmark.preprocess import project

    rng = np.random.default_rng(0)
    image = rng.random((3, 32, 32)).astype(np.float32)  # [marker, DAPI, autofluorescence]
    image[2, 5, 5] = 100.0  # bright only in the autofluorescence channel
    every = project(image, 1, "max", 1, 0)
    marker_only = project(image, 1, "max", 1, 0, cell_idx=[0])
    assert every[0, 5, 5] == 65535
    assert marker_only[0, 5, 5] < 65535
    np.testing.assert_array_equal(every[1], marker_only[1])


# --- round 2 --------------------------------------------------------------------------------


def test_round2_layout():
    from segmentation_benchmark.settings import build_round2

    s = build_round2()
    assert len(s) == 307 and list(s["index"]) == list(range(307))
    blocks = s.groupby(["target", "scope", "cell_channels", "clip_limit"], sort=False).size()
    assert blocks.to_dict() == {
        ("cells", "raw", "markers", 0.0): 56,
        ("cells", "raw", "all", 0.0): 56,
        ("cells", "raw", "membrane", 0.0): 56,
        ("cells", "tissuenet", "markers", 0.0): 56,
        ("nuclei", "all", "markers", 0.0): 56,
        ("cells", "raw", "markers", 0.01): 9,
        ("cells", "tissuenet", "markers", 0.01): 9,
        ("nuclei", "all", "markers", 0.01): 9,
    }
    fixed = s[["projection_method", "low_percentile", "projection_sigma", "gaussian_sigma"]]
    assert (fixed.drop_duplicates().values.tolist()) == [["max", 1, 0, 0]]
    assert not s.drop(columns="index").duplicated().any()


def test_round2_keeps_round1_pairs_in_every_block():
    from segmentation_benchmark.settings import build_round2

    s = build_round2()
    for _, block in s[s["clip_limit"] == 0].groupby(["target", "scope", "cell_channels"]):
        pairs = set(zip(block["flow_threshold"], block["cellprob_threshold"], strict=True))
        assert {(2, -6), (0.4, 0)} <= pairs


def test_committed_round2_csv_matches():
    from segmentation_benchmark.settings import build_round2

    committed = pd.read_csv(Path(settings.__file__).with_name("settings_round2.csv"))
    pd.testing.assert_frame_equal(committed, build_round2(), check_dtype=False)


def test_round1_rows_combine_all_channels():
    assert (build_settings()["cell_channels"] == "all").all()


def test_run_uses_round2_grid_and_channel_selection(bench, monkeypatch):
    run, data, out, _ = bench
    seen = []
    real = run.project

    def spy(image, nuclear, *args, cell_idx=None, **kwargs):
        seen.append(cell_idx)
        return real(image, nuclear, *args, cell_idx=cell_idx, **kwargs)

    monkeypatch.setattr(run, "project", spy)
    crops = pd.read_csv(data / "crops.csv")
    crops["channels"] = "DAPI|CD8|Autofluorescence"
    crops.to_csv(data / "crops.csv", index=False)
    run.run(data, 0, out, grid="round2")  # cells, raw, markers
    assert seen == [[1], [1]]
    assert (out / "results" / "0.csv").exists()
