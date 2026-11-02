"""Tests for bin/write_segmentations.py on a real SpatialData store built in tmp_path."""

import anndata as ad
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import spatialdata as sd
from shapely.geometry import box
from spatialdata.models import Image2DModel, TableModel
from spatialdata.transformations import Scale, get_transformation, set_transformation
from write_segmentations import write_segmentations


@pytest.fixture
def store(tmp_path):
    image = Image2DModel.parse(
        np.ones((2, 64, 64), dtype=np.uint16), dims=("c", "y", "x"), c_coords=["A", "B"], scale_factors=[2]
    )
    set_transformation(image, Scale([0.5, 0.5], axes=("x", "y")), "global")
    proj = Image2DModel.parse(np.ones((1, 64, 64), dtype=np.uint16), dims=("c", "y", "x"), c_coords=["P"])
    path = tmp_path / "sample.zarr"
    sdata = sd.SpatialData(images={"img": image, "img_projected": proj})
    sdata.attrs["cell_segmentation_image"] = "img"
    sdata.write(path)
    return path


def make_shapes(tmp_path, name, n=3):
    gdf = gpd.GeoDataFrame(
        geometry=[box(i * 10, 0, i * 10 + 5, 5) for i in range(n)],
        index=pd.Index([f"c{i}" for i in range(n)], name="cell_id"),
    )
    p = tmp_path / f"{name}.parquet"
    gdf.to_parquet(p)
    return p


def make_table(tmp_path, name, region, n=3):
    obs = pd.DataFrame(
        {"region": pd.Categorical([region] * n), "cell_id": [f"c{i}" for i in range(n)]},
        index=[f"c{i}" for i in range(n)],
    )
    adata = TableModel.parse(
        ad.AnnData(np.arange(n * 2, dtype=float).reshape(n, 2), obs=obs, var=pd.DataFrame(index=["A", "B"])),
        region=region,
        region_key="region",
        instance_key="cell_id",
    )
    p = tmp_path / f"{name}.h5ad"
    adata.write_h5ad(p)
    return p


def inputs(tmp_path):
    return [make_shapes(tmp_path, "cellpose_cells")], [
        make_table(tmp_path, "cellpose_table", "cellpose_cells")
    ]


def test_writes_shapes_and_table(store, tmp_path):
    shapes, tables = inputs(tmp_path)
    write_segmentations(store, shapes, tables)
    out = sd.read_zarr(store)
    assert "cellpose_cells" in out.shapes and "cellpose_table" in out.tables
    assert list(out.shapes["cellpose_cells"].index) == ["c0", "c1", "c2"]
    assert out.shapes["cellpose_cells"].index.name == "cell_id"


def test_shapes_carry_the_image_transformations(store, tmp_path):
    shapes, tables = inputs(tmp_path)
    write_segmentations(store, shapes, tables)
    out = sd.read_zarr(store)

    def matrix(element):
        return get_transformation(element, "global").to_affine_matrix(("x", "y"), ("x", "y"))

    assert matrix(out.shapes["cellpose_cells"]).tolist() == matrix(out.images["img"]).tolist()
    assert matrix(out.shapes["cellpose_cells"])[0, 0] == 0.5


def test_second_run_leaves_one_of_each_with_same_rows(store, tmp_path):
    shapes, tables = inputs(tmp_path)
    write_segmentations(store, shapes, tables)
    first = sd.read_zarr(store)
    rows = (list(first.shapes["cellpose_cells"].index), first.tables["cellpose_table"].X.tolist())
    write_segmentations(store, shapes, tables)
    out = sd.read_zarr(store)
    assert sorted(out.shapes) == ["cellpose_cells"] and sorted(out.tables) == ["cellpose_table"]
    assert (list(out.shapes["cellpose_cells"].index), out.tables["cellpose_table"].X.tolist()) == rows


def test_table_with_missing_region_raises(store, tmp_path):
    shapes = [make_shapes(tmp_path, "cellpose_cells")]
    tables = [make_table(tmp_path, "cellpose_table", "instanseg_cells")]
    with pytest.raises(ValueError, match="cellpose_table.*instanseg_cells"):
        write_segmentations(store, shapes, tables)
    assert "cellpose_cells" not in sd.read_zarr(store).shapes


def test_region_may_be_a_shape_already_in_the_store(store, tmp_path):
    write_segmentations(store, [make_shapes(tmp_path, "cellpose_cells")], [])
    write_segmentations(store, [], [make_table(tmp_path, "cellpose_table", "cellpose_cells")])
    assert "cellpose_table" in sd.read_zarr(store).tables


def test_projection_dropped_by_default(store, tmp_path):
    write_segmentations(store, *inputs(tmp_path))
    assert "img_projected" not in sd.read_zarr(store).images


def test_keep_projection(store, tmp_path):
    write_segmentations(store, *inputs(tmp_path), keep_projection=True)
    assert "img_projected" in sd.read_zarr(store).images


def test_absent_projection_is_a_noop(store, tmp_path):
    write_segmentations(store, *inputs(tmp_path))
    write_segmentations(store, *inputs(tmp_path))
    assert "img" in sd.read_zarr(store).images


def test_missing_segmentation_attribute_raises(store, tmp_path):
    sdata = sd.read_zarr(store)
    del sdata.attrs["cell_segmentation_image"]
    sdata.write_attrs()
    with pytest.raises(ValueError, match="cell_segmentation_image"):
        write_segmentations(store, *inputs(tmp_path))
