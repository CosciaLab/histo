"""Tests for bin/project_channels.py: marker selection, the projection maths, and the
add-then-drop round trip on a real SpatialData store built in tmp_path."""

import json
from pathlib import Path

import numpy as np
import pytest
from project_channels import (
    coarse_level,
    combine,
    dominant,
    percentile_bounds,
    preview_rgb,
    rescale,
    resolve_groups,
    scale_factors_of,
    win_shares,
)
from qc_metrics import read_marker_cycles

REPO = Path(__file__).resolve().parents[2]
EXEMPLAR001 = REPO / "tests" / "exemplar_data" / "markers_exemplar001.csv"


def sheet(tmp_path, text):
    p = tmp_path / "markers.csv"
    p.write_text(text)
    return read_marker_cycles(p)


class TestResolveGroups:
    def test_exemplar_defaults(self):
        """First dna channel only; markers with a membrane or cytoplasm compartment."""
        groups, how = resolve_groups(read_marker_cycles(EXEMPLAR001))
        assert groups["nuclear"] == ["DNA_6"]
        assert groups["cell"] == ["ELANE", "CD57", "CD45", "CD11B", "SMA", "CD16", "ECAD", "NCAM"]
        assert "channel_compartment" in how

    def test_nuclear_only_marker_is_not_cell(self, tmp_path):
        """FOXP3 is nuclear: it belongs in neither default group."""
        rows = sheet(
            tmp_path,
            "channel_number,cycle_number,marker_name,channel_role,channel_compartment\n"
            "1,1,DNA_1,dna,nuclear\n2,1,FOXP3,marker,nuclear\n3,1,CD45,marker,membrane\n",
        )
        groups, _ = resolve_groups(rows)
        assert groups == {"nuclear": ["DNA_1"], "cell": ["CD45"]}

    def test_combined_compartment_counts(self, tmp_path):
        rows = sheet(
            tmp_path,
            "channel_number,cycle_number,marker_name,channel_role,channel_compartment\n"
            "1,1,DNA_1,dna,nuclear\n2,1,KI67,marker,nuclear+cytoplasm\n",
        )
        assert resolve_groups(rows)[0]["cell"] == ["KI67"]

    def test_segmentation_column_overrides(self, tmp_path):
        """Any value in the column makes it the whole selection; blank rows are out."""
        rows = sheet(
            tmp_path,
            "channel_number,cycle_number,marker_name,channel_role,channel_compartment,segmentation\n"
            "1,1,DNA_1,dna,nuclear,nuclear\n"
            "2,1,CD45,marker,membrane,cell\n"
            "3,1,CD3,marker,membrane,\n"
            "4,2,DNA_2,dna,nuclear,nuclear\n"
            "5,2,SMA,marker,cytoplasm,none\n",
        )
        groups, how = resolve_groups(rows)
        assert groups == {"nuclear": ["DNA_1", "DNA_2"], "cell": ["CD45"]}
        assert "segmentation" in how

    def test_segmentation_is_lowercased(self, tmp_path):
        rows = sheet(
            tmp_path,
            "channel_number,cycle_number,marker_name,channel_role,segmentation\n"
            "1,1,DNA_1,dna,Nuclear\n2,1,CD45,marker,CELL\n",
        )
        assert resolve_groups(rows)[0] == {"nuclear": ["DNA_1"], "cell": ["CD45"]}

    def test_empty_cell_group_refused(self, tmp_path):
        rows = sheet(
            tmp_path,
            "channel_number,cycle_number,marker_name,channel_role,channel_compartment\n"
            "1,1,DNA_1,dna,nuclear\n2,1,CD45,marker,\n",
        )
        with pytest.raises(ValueError, match="no channels for 'cell'"):
            resolve_groups(rows)


class TestPercentileBounds:
    def test_bounds(self):
        lo, hi = percentile_bounds(np.arange(1, 102, dtype=np.uint16), 1, 99)
        assert (lo, hi) == pytest.approx((2.0, 100.0))

    def test_zeros_are_ignored(self):
        """Ashlar pads unregistered areas with exact zeros; they are not background."""
        values = np.concatenate([np.zeros(1000, dtype=np.uint16), np.arange(1, 102, dtype=np.uint16)])
        lo, _ = percentile_bounds(values, 1, 99)
        assert lo == pytest.approx(2.0)

    def test_all_zero_returns_none(self):
        assert percentile_bounds(np.zeros(50, dtype=np.uint16), 1, 99.9) is None

    def test_constant_returns_none(self):
        """A flat channel cannot be rescaled; the caller drops it."""
        assert percentile_bounds(np.full(50, 7, dtype=np.uint16), 1, 99.9) is None


class TestRescale:
    def test_maps_bounds_to_unit_range_and_clips(self):
        out = rescale(np.array([0, 10, 60, 110, 500], dtype=np.uint16), 10.0, 110.0)
        assert out.dtype == np.float32
        np.testing.assert_allclose(out, [0, 0, 0.5, 1, 1])


class TestWinShares:
    def test_share_of_pixels_each_marker_is_brightest_in(self):
        a = np.array([[0.9, 0.9], [0.9, 0.1]])
        b = np.array([[0.1, 0.2], [0.3, 0.8]])
        assert win_shares([a, b], mask=None) == pytest.approx([0.75, 0.25])

    def test_pixels_dark_in_every_marker_do_not_count(self):
        """Glass and padding would otherwise go to whichever marker comes first."""
        a = np.array([[0.0, 0.5]])
        b = np.array([[0.0, 0.1]])
        assert win_shares([a, b], mask=None) == pytest.approx([1.0, 0.0])

    def test_only_tissue_counts(self):
        a = np.array([[0.9, 0.1]])
        b = np.array([[0.1, 0.9]])
        assert win_shares([a, b], mask=np.array([[False, True]])) == pytest.approx([0.0, 1.0])

    def test_all_dark_gives_zeros(self):
        assert win_shares([np.zeros((2, 2)), np.zeros((2, 2))], mask=None) == [0.0, 0.0]


class TestDominant:
    def test_a_marker_winning_most_of_a_group_is_flagged(self):
        channels = {
            "nuclear": [{"marker": "DNA_1", "win_share": 1.0}],
            "cell": [{"marker": "LDH", "win_share": 0.85}, {"marker": "CD45", "win_share": 0.15}],
        }
        assert dominant(channels) == [{"channel": "cell", "marker": "LDH", "win_share": 0.85}]

    def test_a_single_marker_group_is_not_flagged(self):
        assert dominant({"nuclear": [{"marker": "DNA_1", "win_share": 1.0}]}) == []


class TestCombine:
    stack = np.array([[[0.0, 1.0]], [[0.5, 0.0]]], dtype=np.float32)

    def test_max(self):
        np.testing.assert_allclose(combine(self.stack, "max"), [[0.5, 1.0]])

    def test_mean(self):
        np.testing.assert_allclose(combine(self.stack, "mean"), [[0.25, 0.5]])

    def test_unknown_method_refused(self):
        with pytest.raises(ValueError, match="unknown method"):
            combine(self.stack, "median")


class TestPyramid:
    def test_scale_factors(self):
        shapes = [(3139, 2511), (1569, 1255), (784, 627), (392, 313), (196, 156)]
        assert scale_factors_of(shapes) == [2, 2, 2, 2]

    def test_single_level(self):
        assert scale_factors_of([(100, 100)]) == []

    def test_coarse_level_keeps_long_side(self):
        shapes = [(40000, 30000), (20000, 15000), (10000, 7500), (5000, 3750), (2500, 1875), (1250, 937)]
        assert coarse_level(shapes, min_side=2000) == 4

    def test_coarse_level_small_image_uses_full_resolution(self):
        assert coarse_level([(1500, 1000), (750, 500)], min_side=2000) == 0


class TestPreview:
    def test_nuclear_magenta_cell_green(self):
        nuclear = np.array([[1.0, 0.0]], dtype=np.float32)
        cell = np.array([[0.0, 1.0]], dtype=np.float32)
        rgb = preview_rgb(nuclear, cell)
        assert rgb.dtype == np.uint8
        assert rgb[0, 0].tolist() == [255, 0, 255]
        assert rgb[0, 1].tolist() == [0, 255, 0]


# Store round trip -----------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    """A 4-channel 64x64 store with a 2-level pyramid, named like the real exemplar."""
    import spatialdata as sd
    from spatialdata.models import Image2DModel

    rng = np.random.default_rng(0)
    data = rng.integers(0, 1000, size=(4, 64, 64), dtype=np.uint16)
    data[3] = 5  # constant channel
    image = Image2DModel.parse(
        data,
        dims=("c", "y", "x"),
        c_coords=["DNA_1", "CD45", "ECAD", "FLAT"],
        scale_factors=[2],
        chunks=(1, 32, 32),
    )
    path = tmp_path / "sample.zarr"
    sdata = sd.SpatialData(images={"sample": image})
    sdata.attrs["cell_segmentation_image"] = "sample"
    sdata.write(path)
    return path


def markers(tmp_path, cell="CD45,ECAD,FLAT"):
    rows = ["channel_number,cycle_number,marker_name,channel_role,segmentation", "1,1,DNA_1,dna,nuclear"]
    names = ["DNA_1", "CD45", "ECAD", "FLAT"]
    for i, n in enumerate(names[1:], start=2):
        rows.append(f"{i},1,{n},marker,{'cell' if n in cell.split(',') else ''}")
    p = tmp_path / "markers.csv"
    p.write_text("\n".join(rows) + "\n")
    return p


class TestStoreRoundTrip:
    def test_project_then_drop(self, store, tmp_path, monkeypatch):
        import spatialdata as sd
        from project_channels import drop, project

        monkeypatch.chdir(tmp_path)
        summary = project(
            store, markers(tmp_path), method="max", low=1, high=99.9, sigma=1.0, prefix="sample"
        )

        s = sd.read_zarr(store)
        assert s.attrs["cell_segmentation_image"] == "sample_projected"
        assert s.attrs["histo_projection_source"] == "sample"
        level0 = next(iter(s["sample_projected"]["scale0"].values()))
        assert list(level0.c.values) == ["nuclear", "cell"]
        assert level0.dtype == np.uint16
        assert level0.shape == (2, 64, 64)
        assert len(s["sample_projected"]) == 2  # same pyramid depth as the source

        assert summary["dropped_constant"] == ["FLAT"]
        assert [c["marker"] for c in summary["channels"]["cell"]] == ["CD45", "ECAD"]
        assert sum(c["win_share"] for c in summary["channels"]["cell"]) == pytest.approx(1.0)
        assert summary["channels"]["nuclear"][0]["win_share"] == pytest.approx(1.0)
        assert json.loads((tmp_path / "sample_projection.json").read_text()) == summary
        assert (tmp_path / "sample_projection.png").stat().st_size > 0

        drop(store)
        s = sd.read_zarr(store)
        assert list(s.images) == ["sample"]
        assert s.attrs["cell_segmentation_image"] == "sample"
        assert "histo_projection_source" not in s.attrs

    def test_drop_keep_leaves_the_projection_beside_the_source(self, store, tmp_path, monkeypatch):
        """keep_projection: AGGREGATE and QC follow the attribute back to the full image."""
        import spatialdata as sd
        from project_channels import drop, project

        monkeypatch.chdir(tmp_path)
        project(store, markers(tmp_path), method="max", low=1, high=99.9, sigma=0, prefix="sample")
        drop(store, keep=True)

        s = sd.read_zarr(store)
        assert sorted(s.images) == ["sample", "sample_projected"]
        assert s.attrs["cell_segmentation_image"] == "sample"
        assert "histo_projection_source" not in s.attrs

    def test_project_is_rerunnable(self, store, tmp_path, monkeypatch):
        """A retried task meets the store it already mutated; it must not stack projections."""
        import spatialdata as sd
        from project_channels import project

        monkeypatch.chdir(tmp_path)
        m = markers(tmp_path)
        project(store, m, method="max", low=1, high=99.9, sigma=0, prefix="sample")
        project(store, m, method="mean", low=1, high=99.9, sigma=0, prefix="sample")

        s = sd.read_zarr(store)
        assert sorted(s.images) == ["sample", "sample_projected"]
        assert s.attrs["histo_projection_source"] == "sample"
        # Unsmoothed, the high percentile saturates: the full uint16 range is used.
        level0 = next(iter(s["sample_projected"]["scale0"].values()))
        assert int(level0.data.max().compute()) == 65535

    def test_unknown_marker_refused(self, store, tmp_path, monkeypatch):
        from project_channels import project

        monkeypatch.chdir(tmp_path)
        p = tmp_path / "bad.csv"
        p.write_text(
            "channel_number,cycle_number,marker_name,channel_role,segmentation\n"
            "1,1,DNA_1,dna,nuclear\n2,1,CD3,marker,cell\n"
        )
        with pytest.raises(ValueError, match="CD3"):
            project(store, p, method="max", low=1, high=99.9, sigma=0, prefix="sample")

    def test_drop_without_projection_refused(self, store):
        from project_channels import drop

        with pytest.raises(ValueError, match="no projection"):
            drop(store)

    def test_percentiles_come_from_tissue_only(self, tmp_path, monkeypatch):
        """With tissue segmentation, glass outside the ROI must not set the bounds."""
        import geopandas as gpd
        import spatialdata as sd
        from project_channels import project
        from shapely.geometry import box
        from spatialdata.models import Image2DModel, ShapesModel

        data = np.full((2, 64, 64), 50, dtype=np.uint16)  # glass
        data[:, :, 32:] = np.arange(1, 32 * 64 + 1, dtype=np.uint16).reshape(64, 32)  # tissue, right half
        image = Image2DModel.parse(data, dims=("c", "y", "x"), c_coords=["DNA_1", "CD45"], chunks=(1, 32, 32))
        roi = ShapesModel.parse(gpd.GeoDataFrame(geometry=[box(32, 0, 64, 64)]))
        path = tmp_path / "roi.zarr"
        sd.SpatialData(images={"sample": image}, shapes={"region_of_interest": roi}).write(path)
        sheet = tmp_path / "m.csv"
        sheet.write_text(
            "channel_number,cycle_number,marker_name,channel_role,channel_compartment\n"
            "1,1,DNA_1,dna,nuclear\n2,1,CD45,marker,membrane\n"
        )

        monkeypatch.chdir(tmp_path)
        summary = project(path, sheet, method="max", low=1, high=99.9, sigma=0, prefix="roi")

        assert summary["tissue_masked"] is True
        lo = summary["channels"]["cell"][0]["lo"]
        # The glass value 50 would be the 1st percentile of the whole image.
        assert lo == pytest.approx(np.percentile(np.arange(1, 32 * 64 + 1), 1))
