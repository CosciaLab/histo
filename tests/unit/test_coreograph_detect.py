"""Tests for the reading and metrics half of coreograph_detect.py (no TensorFlow needed)."""

import itertools
import json

import coreograph_detect
import numpy as np
import pytest
import tifffile
from coreograph_detect import centroids_full_res, core_metrics, main, pixel_size_um, read_downsampled

ARR = np.zeros((2, 32, 32), dtype=np.uint16)


def write_ome(tmp_path, arr, physical_size=0.65, unit="µm", name="img.ome.tif"):
    metadata = {"axes": "CYX" if arr.ndim == 3 else "YX"}
    if physical_size is not None:
        metadata["PhysicalSizeX"] = physical_size
        metadata["PhysicalSizeY"] = physical_size
    if unit is not None:
        metadata["PhysicalSizeXUnit"] = unit
        metadata["PhysicalSizeYUnit"] = unit
    p = tmp_path / name
    tifffile.imwrite(p, arr, ome=True, metadata=metadata)
    return p


def discs(centres, r, shape):
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    labels = np.zeros(shape, dtype=np.int32)
    for i, (cy, cx) in enumerate(centres, start=1):
        labels[(yy - cy) ** 2 + (xx - cx) ** 2 <= r**2] = i
    return labels


def reference_halvings(a, k):
    """Coreograph's k cv2 INTER_NEAREST halvings: output pixel i comes from input 2i."""
    for _ in range(k):
        a = a[::2, ::2][: a.shape[0] // 2, : a.shape[1] // 2]
    return a


class TestReadDownsampled:
    @pytest.mark.parametrize("k", [0, 1, 3])
    def test_matches_repeated_halving_odd_shape(self, tmp_path, k):
        arr = np.arange(3 * 101 * 77, dtype=np.uint16).reshape(3, 101, 77)
        p = write_ome(tmp_path, arr)
        assert np.array_equal(read_downsampled(p, 1, k), reference_halvings(arr[1], k))

    def test_single_channel(self, tmp_path):
        arr = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64)
        assert read_downsampled(write_ome(tmp_path, arr), 0, 2).shape == (16, 16)


class TestPixelSize:
    def test_microns(self, tmp_path):
        assert pixel_size_um(write_ome(tmp_path, ARR, 0.65)) == pytest.approx(0.65)

    @pytest.mark.parametrize(
        "value,unit,expected", [(650, "nm", 0.65), (0.00065, "mm", 0.65), (0.65, None, 0.65)]
    )
    def test_units(self, tmp_path, value, unit, expected):
        """OME's default unit is µm; nm and mm are converted."""
        assert pixel_size_um(write_ome(tmp_path, ARR, value, unit)) == pytest.approx(expected)

    def test_missing_fails(self, tmp_path):
        with pytest.raises(ValueError, match="pixel size"):
            pixel_size_um(write_ome(tmp_path, ARR, None, None))

    def test_unknown_unit_fails(self, tmp_path):
        with pytest.raises(ValueError, match="pixel size"):
            pixel_size_um(write_ome(tmp_path, ARR, 0.65, "pixel"))


class TestCoreMetrics:
    def test_four_discs(self):
        # k=2, 0.5 µm/px: radius 50 px at k → diameter 100 px × 4 × 0.5 µm = 0.2 mm
        labels = discs([(100, 100), (100, 300), (300, 100), (300, 300)], 50, (400, 400))
        m = core_metrics(labels, est_core_diam_px=120, k=2, pixel_um=0.5, expected_cores=4, diameter_mm=0.2)
        assert m["k"] == 2
        assert m["n_cores"] == 4 and m["count_error"] == 0
        assert m["diam_mm"] == pytest.approx(0.2, rel=0.02)
        assert m["diam_error"] < 0.02 and m["size_cv"] < 0.02
        assert m["crop_ratio"] == pytest.approx(1.2)
        assert m["core_px_at_k"] == pytest.approx(100)
        assert m["um_per_px"] == pytest.approx(2.0)

    def test_merged_blob_raises_size_cv(self):
        labels = discs([(100, 100), (300, 100), (300, 300)], 50, (400, 400))
        labels[labels == 1] = 0
        labels[50:150, 50:350] = 1  # one blob spanning two core positions
        m = core_metrics(labels, 120, 2, 0.5, 4, 0.2)
        assert m["n_cores"] == 3 and m["count_error"] == pytest.approx(0.25)
        assert m["size_cv"] > 0.3

    def test_zero_cores(self):
        m = core_metrics(np.zeros((50, 50), np.int32), 0, 3, 0.65, 4, 1.5)
        assert m["n_cores"] == 0 and m["count_error"] == 1
        assert m["diam_mm"] is None and m["diam_error"] is None
        assert m["size_cv"] is None and m["crop_ratio"] is None

    def test_json_serialisable(self):
        """Metrics go to JSON; numpy scalars would not serialise."""
        import json

        labels = discs([(20, 20)], 5, (40, 40))
        json.dumps(core_metrics(labels, 12.0, 3, 0.65, 1, 0.1))


def test_centroids_scaled_to_full_res():
    labels = discs([(10, 20)], 3, (40, 40))
    assert np.allclose(centroids_full_res(labels, 3), [[80, 160]])


CENTRES = [(16, 16), (16, 48), (48, 16), (48, 48)]


def argv(image):
    return [
        "--image", str(image), "--downsample-factor", "3", "--channel", "0", "--sensitivity", "0.3",
        "--buffer", "2", "--expected-cores", "4", "--core-diameter-mm", "1.5", "--prefix", "slide",
    ]  # fmt: skip


class TestMain:
    """main() with detect_labels patched out, so no TensorFlow is needed."""

    def test_writes_four_outputs(self, tmp_path, monkeypatch):
        img = write_ome(tmp_path, np.zeros((2, 512, 512), np.uint16), 0.65)
        monkeypatch.setattr(
            coreograph_detect, "detect_labels", lambda im, *_: (discs(CENTRES, 10, im.shape), 30.0)
        )
        monkeypatch.chdir(tmp_path)
        main(argv(img))
        m = json.loads((tmp_path / "slide_k3_metrics.json").read_text())
        assert m["k"] == 3 and m["n_cores"] == 4 and m["pixel_um"] == pytest.approx(0.65)
        for suffix in ["coremask.tif", "centroids.txt", "overlay.png"]:
            assert (tmp_path / f"slide_k3_{suffix}").stat().st_size > 0

    def test_detect_sees_downsampled_channel(self, tmp_path, monkeypatch):
        arr = np.zeros((2, 512, 512), np.uint16)
        arr[0] = 7
        seen = {}

        def fake(im, s, b):
            seen.update(shape=im.shape, value=int(im.max()), sensitivity=s, buffer=b)
            return discs(CENTRES, 10, im.shape), 30.0

        monkeypatch.setattr(coreograph_detect, "detect_labels", fake)
        monkeypatch.chdir(tmp_path)
        main(argv(write_ome(tmp_path, arr, 0.65)))
        assert seen == {"shape": (64, 64), "value": 7, "sensitivity": 0.3, "buffer": 2.0}

    def test_centroids_in_coreograph_format(self, tmp_path, monkeypatch):
        img = write_ome(tmp_path, np.zeros((2, 512, 512), np.uint16), 0.65)
        monkeypatch.setattr(
            coreograph_detect, "detect_labels", lambda im, *_: (discs(CENTRES, 10, im.shape), 30.0)
        )
        monkeypatch.chdir(tmp_path)
        main(argv(img))
        lines = (tmp_path / "slide_k3_centroids.txt").read_text().splitlines()
        assert lines[0] == f"{128:10.5f} {128:10.5f}"
        assert len(lines) == 4

    def test_coremask_keeps_labels_above_255(self, tmp_path, monkeypatch):
        labels = np.zeros((120, 90), np.int32)
        for i, (y, x) in enumerate(itertools.product(range(0, 120, 6), range(0, 90, 6)), start=1):
            labels[y : y + 3, x : x + 3] = i  # 20 × 15 = 300 squares
        img = write_ome(tmp_path, np.zeros((2, 960, 720), np.uint16), 0.65)
        monkeypatch.setattr(coreograph_detect, "detect_labels", lambda *_: (labels, 3.0))
        monkeypatch.chdir(tmp_path)
        main(argv(img))
        assert tifffile.TiffFile(tmp_path / "slide_k3_coremask.tif").asarray().max() == 300
        assert json.loads((tmp_path / "slide_k3_metrics.json").read_text())["n_cores"] == 300

    def test_exits_with_message_without_pixel_size(self, tmp_path, monkeypatch):
        img = write_ome(tmp_path, np.zeros((2, 64, 64), np.uint16), None, None)
        monkeypatch.setattr(
            coreograph_detect, "detect_labels", lambda im, *_: (discs(CENTRES, 10, im.shape), 30.0)
        )
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit, match="pixel size"):
            main(argv(img))
