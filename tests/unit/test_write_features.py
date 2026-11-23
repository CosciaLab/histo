"""Tests for bin/write_features.py on a real SpatialData store built in tmp_path."""

import anndata as ad
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import spatialdata as sd
from shapely.geometry import box
from spatialdata.models import Image2DModel, ShapesModel, TableModel
from write_features import write_features
from write_segmentations import RESERVED, write_segmentations

IDS = ["c0", "c1", "c2"]


def parsed_table(ids, var, region="cellpose_cells", uns=None):
    obs = pd.DataFrame({"region": pd.Categorical([region] * len(ids)), "cell_id": ids}, index=ids)
    adata = ad.AnnData(np.ones((len(ids), len(var)), dtype="float32"), obs=obs, var=pd.DataFrame(index=var))
    adata.uns.update(uns or {})
    return TableModel.parse(adata, region=region, region_key="region", instance_key="cell_id")


@pytest.fixture
def store(tmp_path):
    image = Image2DModel.parse(
        np.ones((2, 64, 64), dtype=np.uint16), dims=("c", "y", "x"), c_coords=["A", "B"]
    )
    shapes = ShapesModel.parse(
        gpd.GeoDataFrame(
            geometry=[box(i * 10, 0, i * 10 + 5, 5) for i in range(3)],
            index=pd.Index(IDS, name="cell_id"),
        )
    )
    path = tmp_path / "sample.zarr"
    sdata = sd.SpatialData(
        images={"img": image},
        shapes={"cellpose_cells": shapes},
        tables={"cellpose_table": parsed_table(IDS, ["A", "B"])},
    )
    sdata.attrs["cell_segmentation_image"] = "img"
    sdata.write(path)
    return path


def nimbus_h5ad(tmp_path, ids=IDS):
    p = tmp_path / "cellpose_nimbus.h5ad"
    parsed_table(ids, ["A", "B"], uns={"nimbus": {"version": "0.0.5"}}).write_h5ad(p)
    return p


def test_writes_table_and_uns(store, tmp_path):
    write_features(store, [nimbus_h5ad(tmp_path)])
    out = sd.read_zarr(store)
    assert "cellpose_nimbus" in out.tables
    assert list(out.tables["cellpose_nimbus"].obs_names) == IDS
    assert out.tables["cellpose_nimbus"].uns["nimbus"]["version"] == "0.0.5"
    assert "cellpose_table" in out.tables


def test_refuses_row_mismatch(store, tmp_path):
    for ids in (["c2", "c1", "c0"], ["c0", "c1"]):
        with pytest.raises(ValueError, match="cellpose_nimbus.*cellpose_table"):
            write_features(store, [nimbus_h5ad(tmp_path, ids)])
    assert "cellpose_nimbus" not in sd.read_zarr(store).tables


def test_rerun_is_idempotent(store, tmp_path):
    h5ad = nimbus_h5ad(tmp_path)
    write_features(store, [h5ad])
    write_features(store, [h5ad])
    out = sd.read_zarr(store)
    assert sorted(out.tables) == ["cellpose_nimbus", "cellpose_table"]


def test_write_segmentations_removes_stale_nimbus(store, tmp_path):
    write_features(store, [nimbus_h5ad(tmp_path)])
    assert RESERVED.match("cellpose_nimbus")
    table = tmp_path / "cellpose_table.h5ad"
    parsed_table(IDS, ["A", "B"]).write_h5ad(table)
    write_segmentations(store, [], [table])
    assert "cellpose_nimbus" not in sd.read_zarr(store).tables
