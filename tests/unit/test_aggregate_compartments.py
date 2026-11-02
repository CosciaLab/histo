"""Tests for aggregate_compartments.py: hole-aware means, table assembly, obs labels."""

import numpy as np
import pytest
from aggregate_compartments import build_table, compartment_layer, label_cells, mean_intensities, rasterize

pd = pytest.importorskip("pandas", reason="needs pandas")
gpd = pytest.importorskip("geopandas", reason="needs geopandas")
xr = pytest.importorskip("xarray", reason="needs xarray")
pytest.importorskip("dask", reason="needs dask")
pytest.importorskip("anndata", reason="needs anndata")
pytest.importorskip("spatialdata", reason="needs spatialdata")
from shapely.geometry import MultiPolygon, Point, Polygon, box  # noqa: E402


def make_image(arrays, chunks=None):
    """(c, y, x) DataArray with a `c` coordinate, dask-backed as in the store."""
    import dask.array as da

    data = np.stack(arrays).astype(float)
    return xr.DataArray(
        da.from_array(data, chunks=chunks or data.shape),
        dims=("c", "y", "x"),
        coords={"c": [f"ch{i}" for i in range(len(arrays))]},
    )


def bright_centre_image():
    """20x20, 10 everywhere except 100 in the central 6x6 square (7..13)."""
    img = np.full((20, 20), 10.0)
    img[7:13, 7:13] = 100.0
    return make_image([img])


def frame(geoms, names=None):
    names = names or [f"cell_{i}" for i in range(len(geoms))]
    return gpd.GeoDataFrame(geometry=geoms, index=pd.Index(names, name="cell_id"))


class TestRasterize:
    def test_hole_is_zero(self):
        ring = Polygon(box(2, 2, 18, 18).exterior.coords, [box(7, 7, 13, 13).exterior.coords])
        mask = rasterize(ring, (20, 20))
        assert mask[10, 10] == 0
        assert mask[3, 3] == 1

    def test_multipolygon_parts_each_get_their_hole(self):
        a = Polygon(box(0, 0, 10, 10).exterior.coords, [box(3, 3, 6, 6).exterior.coords])
        b = box(12, 12, 18, 18)
        mask = rasterize(MultiPolygon([a, b]), (20, 20))
        assert mask[4, 4] == 0 and mask[1, 1] == 1 and mask[15, 15] == 1


class TestMeanIntensities:
    def test_ring_mean_excludes_hole(self):
        # Polygons touch their boundary pixels (17x17 = 289 px). Exterior-only filling would
        # average ~21.2 here (the ideal 16x16 square: (36*100 + 220*10)/256 = 22.7); the ring is all 10.
        ring = Polygon(box(2, 2, 18, 18).exterior.coords, [box(7, 7, 13, 13).exterior.coords])
        out = mean_intensities(bright_centre_image(), frame([ring]))
        assert out.shape == (1, 1)
        assert out[0, 0] == pytest.approx(10)

    def test_solid_square_includes_centre(self):
        out = mean_intensities(bright_centre_image(), frame([box(2, 2, 18, 18)]))
        assert out[0, 0] == pytest.approx(10 + 90 * 36 / 289)

    def test_multipolygon_averages_both_parts(self):
        img = np.zeros((20, 20))
        img[0:5, 0:5] = 10  # boundary pixels are touched, so 5x5
        img[10:15, 10:15] = 30
        parts = MultiPolygon([box(0, 0, 4, 4), box(10, 10, 14, 14)])
        out = mean_intensities(make_image([img]), frame([parts]))
        assert out[0, 0] == pytest.approx(20)

    def test_two_channels_and_chunks(self):
        a, b = np.full((20, 20), 1.0), np.full((20, 20), 2.0)
        out = mean_intensities(
            make_image([a, b], chunks=(2, 8, 8)), frame([box(3, 3, 15, 15), box(0, 0, 5, 5)])
        )
        assert out.shape == (2, 2)
        np.testing.assert_allclose(out, [[1, 2], [1, 2]])

    def test_no_shapes(self):
        out = mean_intensities(bright_centre_image(), frame([]))
        assert out.shape == (0, 1)


class TestCompartmentLayer:
    def test_missing_cells_are_nan(self):
        cells = frame([box(0, 0, 4, 4), box(10, 10, 14, 14)], ["a_0", "a_1"])
        out = compartment_layer(bright_centre_image(), cells.iloc[[1]], cells)
        assert np.isnan(out[0]).all() and not np.isnan(out[1]).any()

    def test_empty_compartment_is_all_nan(self):
        cells = frame([box(0, 0, 4, 4)], ["a_0"])
        assert np.isnan(compartment_layer(bright_centre_image(), frame([]), cells)).all()


def position_image(h=40, w=40):
    """value = y*w + x, so any mask/pixel offset changes the mean."""
    return np.arange(h * w, dtype=float).reshape(1, h, w)


class TestChunkEdges:
    def test_chunked_equals_single_chunk(self):
        round_cell = Point(19.5, 19.5).buffer(7)
        two_part = MultiPolygon([box(14, 3, 22, 9), box(16, 30, 26, 37)])
        ring = Polygon(box(10, 10, 30, 30).exterior.coords, [box(15, 15, 25, 25).exterior.coords])
        shapes = frame([round_cell, two_part, ring])
        data = position_image()
        want = mean_intensities(make_image(list(data)), shapes)
        got = mean_intensities(make_image(list(data), chunks=(1, 16, 16)), shapes)
        np.testing.assert_allclose(got, want)

    def test_empty_mask_is_nan(self):
        tiny = box(5.2, 5.2, 5.4, 5.4)  # touches no pixel centre
        out = mean_intensities(bright_centre_image(), frame([tiny, box(0, 0, 4, 4)]))
        assert np.isnan(out[0, 0]) and not np.isnan(out[1, 0])


class TestRasterizeParts:
    def test_island_in_lake_listed_first_survives(self):
        island = box(8, 8, 12, 12)
        lake = Polygon(box(2, 2, 18, 18).exterior.coords, [box(5, 5, 15, 15).exterior.coords])
        mask = rasterize(MultiPolygon([island, lake]), (20, 20))
        assert mask[10, 10] == 1 and mask[6, 6] == 0 and mask[3, 3] == 1


def three_cells():
    return frame([box(0, 0, 4, 4), box(5, 5, 9, 9), box(10, 10, 14, 14)], ["a_0", "a_1", "a_2"])


SPEC = {"name": "cellpose_cells", "target": "cells", "method": "cellpose", "diameter": 30, "channels": None}


def table(**kw):
    args = dict(
        cells=three_cells(),
        x=np.ones((3, 2)),
        var_names=["DAPI", "CD3"],
        layers={},
        obs_extra=None,
        region="cellpose_cells",
        slide="TMA01",
        core_id=None,
        specs=[SPEC],
    )
    args.update(kw)
    return build_table(**args)


class TestBuildTable:
    def test_obs_names_are_cell_index(self):
        t = table()
        assert list(t.obs_names) == ["a_0", "a_1", "a_2"]
        assert list(t.obs["cell_id"]) == ["a_0", "a_1", "a_2"]
        assert list(t.var_names) == ["DAPI", "CD3"]

    def test_sopa_obs_columns(self):
        t = table()
        assert isinstance(t.obs["region"].dtype, pd.CategoricalDtype)
        assert list(t.obs["region"].unique()) == ["cellpose_cells"]
        np.testing.assert_allclose(t.obs["area"], [16, 16, 16])
        assert t.obsm["spatial"].shape == (3, 2)
        np.testing.assert_allclose(t.obsm["spatial"][0], [2, 2])

    def test_slide_categorical_and_core_id_only_when_given(self):
        t = table()
        assert isinstance(t.obs["slide"].dtype, pd.CategoricalDtype)
        assert "core_id" not in t.obs
        assert list(table(core_id="TMA01_core001").obs["core_id"].unique()) == ["TMA01_core001"]

    def test_table_model_attrs(self):
        attrs = table().uns["spatialdata_attrs"]
        assert attrs["region"] == "cellpose_cells"
        assert attrs["region_key"] == "region"
        assert attrs["instance_key"] == "cell_id"

    def test_no_layers_by_default(self):
        assert [k for k in table().layers if k is not None] == []

    def test_layers_and_obs_extra(self):
        nuc = np.full((3, 2), np.nan)
        extra = pd.DataFrame({"n_nuclei": [1, 0, 2]}, index=three_cells().index)
        t = table(layers={"nucleus": nuc, "cytoplasm": np.zeros((3, 2))}, obs_extra=extra)
        assert set(t.layers) - {None} == {"nucleus", "cytoplasm"}
        assert np.isnan(t.layers["nucleus"]).all()
        assert list(t.obs["n_nuclei"]) == [1, 0, 2]

    def test_specs_keyed_by_name_without_none(self):
        seg = table().uns["segmentation"]
        assert seg == {
            "cellpose_cells": {
                "name": "cellpose_cells",
                "target": "cells",
                "method": "cellpose",
                "diameter": 30,
            }
        }

    def test_specs_round_trip_h5ad(self, tmp_path):
        import anndata as ad

        t = table(core_id="TMA01_core001")
        t.write_h5ad(tmp_path / "t.h5ad")
        back = ad.read_h5ad(tmp_path / "t.h5ad")
        assert back.uns["segmentation"]["cellpose_cells"]["diameter"] == 30
        assert list(back.obs_names) == ["a_0", "a_1", "a_2"]

    def test_mismatched_rows_refused(self):
        with pytest.raises(ValueError, match="rows"):
            table(x=np.ones((2, 2)))


def sopa_obs(n=3):
    """obs as sopa's aggregation leaves it: slide is the image element name."""
    return pd.DataFrame({"slide": pd.Categorical(["TMA01_core001_backsub"] * n), "area": [1.0] * n})


class TestLabelCells:
    def test_slide_replaces_sopa_value(self):
        obs = label_cells(sopa_obs(), slide="TMA01")
        assert list(obs["slide"]) == ["TMA01"] * 3

    def test_core_id_written_on_tma(self):
        obs = label_cells(sopa_obs(), slide="TMA01", core_id="TMA01_core001")
        assert list(obs["core_id"]) == ["TMA01_core001"] * 3

    def test_no_core_id_column_off_tma(self):
        """Its absence is what says the cells did not come from a TMA."""
        obs = label_cells(sopa_obs(), slide="WSI01")
        assert "core_id" not in obs

    def test_columns_are_categorical(self):
        """Matches sopa's dtype, so concatenated tables stay compact."""
        obs = label_cells(sopa_obs(), slide="TMA01", core_id="TMA01_core001")
        assert isinstance(obs["slide"].dtype, pd.CategoricalDtype)
        assert isinstance(obs["core_id"].dtype, pd.CategoricalDtype)

    def test_other_columns_untouched(self):
        obs = label_cells(sopa_obs(), slide="TMA01")
        assert list(obs["area"]) == [1.0] * 3

    def test_empty_table(self):
        """A core with no cells still gets the columns."""
        obs = label_cells(sopa_obs(n=0), slide="TMA01", core_id="TMA01_core001")
        assert {"slide", "core_id"} <= set(obs.columns)
        assert len(obs) == 0

    def test_blank_slide_refused(self):
        with pytest.raises(ValueError, match="slide"):
            label_cells(sopa_obs(), slide="")
