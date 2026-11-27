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
    args = ([niche_h5ad(tmp_path), tissue_h5ad(tmp_path)], [niche_parquet(tmp_path)])
    write_features(store, *args)
    write_features(store, *args)
    out = sd.read_zarr(store)
    assert sorted(out.shapes) == ["cellpose_cells", "virtues_niches"]
    assert sorted(out.tables) == [
        "cellpose_nimbus",
        "cellpose_table",
        "virtues_niches_table",
        "virtues_tissue",
    ]


def test_write_segmentations_removes_stale_nimbus(store, tmp_path):
    write_features(store, [nimbus_h5ad(tmp_path)])
    assert RESERVED.match("cellpose_nimbus")
    table = tmp_path / "cellpose_table.h5ad"
    parsed_table(IDS, ["A", "B"]).write_h5ad(table)
    write_segmentations(store, [], [table])
    assert "cellpose_nimbus" not in sd.read_zarr(store).tables


NICHES = ["niche_0", "niche_1"]


def niche_parquet(tmp_path, ids=NICHES):
    p = tmp_path / "virtues_niches.parquet"
    gpd.GeoDataFrame(
        geometry=[box(i * 20, 0, i * 20 + 16, 16) for i in range(len(ids))], index=pd.Index(ids)
    ).to_parquet(p)
    return p


def niche_h5ad(tmp_path, ids=NICHES):
    p = tmp_path / "virtues_niches_table.h5ad"
    obs = pd.DataFrame({"region": pd.Categorical(["virtues_niches"] * len(ids)), "niche_id": ids}, index=ids)
    adata = ad.AnnData(np.ones((len(ids), 4), dtype="float32"), obs=obs)
    TableModel.parse(adata, region="virtues_niches", region_key="region", instance_key="niche_id").write_h5ad(
        p
    )
    return p


def tissue_h5ad(tmp_path):
    p = tmp_path / "virtues_tissue.h5ad"
    adata = ad.AnnData(
        np.ones((1, 4), dtype="float32"), obs=pd.DataFrame({"slide": ["s"]}, index=["tissue_0"])
    )
    TableModel.parse(adata).write_h5ad(p)
    return p


def test_writes_niches_shapes_and_table(store, tmp_path):
    write_features(store, [niche_h5ad(tmp_path)], [niche_parquet(tmp_path)])
    out = sd.read_zarr(store)
    assert list(out.shapes["virtues_niches"].index) == NICHES
    assert list(out.tables["virtues_niches_table"].obs_names) == NICHES
    assert out.tables["virtues_niches_table"].uns["spatialdata_attrs"]["region"] == "virtues_niches"


def test_writes_unannotated_tissue_table(store, tmp_path):
    write_features(store, [tissue_h5ad(tmp_path)])
    out = sd.read_zarr(store)
    assert list(out.tables["virtues_tissue"].obs_names) == ["tissue_0"]
    assert "region" not in out.tables["virtues_tissue"].uns.get("spatialdata_attrs", {})


def test_niche_table_rows_must_match_shapes(store, tmp_path):
    with pytest.raises(ValueError, match="virtues_niches_table"):
        write_features(store, [niche_h5ad(tmp_path, ["niche_1", "niche_0"])], [niche_parquet(tmp_path)])
    with pytest.raises(ValueError, match="virtues_niches_table"):
        write_features(store, [niche_h5ad(tmp_path)], [])
    assert "virtues_niches" not in sd.read_zarr(store).shapes


def test_nimbus_tables_still_checked_against_method_table(store, tmp_path):
    with pytest.raises(ValueError, match="cellpose_nimbus.*cellpose_table"):
        write_features(store, [nimbus_h5ad(tmp_path, ["c1", "c0", "c2"])], [niche_parquet(tmp_path)])


def test_write_segmentations_removes_stale_virtues_elements(store, tmp_path):
    write_features(store, [niche_h5ad(tmp_path), tissue_h5ad(tmp_path)], [niche_parquet(tmp_path)])
    for name in ("virtues_niches", "virtues_niches_table", "virtues_tissue", "cellpose_virtues"):
        assert RESERVED.match(name)
    table = tmp_path / "cellpose_table.h5ad"
    parsed_table(IDS, ["A", "B"]).write_h5ad(table)
    write_segmentations(store, [], [table])
    out = sd.read_zarr(store)
    assert "virtues_niches" not in out.shapes
    assert not {"virtues_niches_table", "virtues_tissue"} & set(out.tables)
