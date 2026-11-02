"""Tests for bin/resolve_segmentation.py: ids, empty patches and the store's image key."""

import json

import geopandas as gpd
import pytest
from resolve_segmentation import assign_ids, check_not_empty, read_patches, store_image_key
from shapely.geometry import box


def frame(n):
    return gpd.GeoDataFrame(geometry=[box(i * 10, 0, i * 10 + 5, 5) for i in range(n)])


def test_assign_ids_names_index_and_counts_from_zero():
    out = assign_ids(frame(3), "img", "nuclei")
    assert list(out.index) == ["img_nuclei_0", "img_nuclei_1", "img_nuclei_2"]
    assert out.index.name == "cell_id"


def test_assign_ids_ignores_incoming_index():
    cells = frame(2)
    cells.index = [7, 3]
    assert list(assign_ids(cells, "img", "cells").index) == ["img_cells_0", "img_cells_1"]


def test_check_not_empty_names_the_spec():
    with pytest.raises(ValueError, match="segmentation 'instanseg_cells' found no cells"):
        check_not_empty(frame(0), "instanseg_cells")
    check_not_empty(frame(1), "instanseg_cells")


def test_read_patches_skips_zero_byte_and_zero_row_files(tmp_path):
    frame(2).to_parquet(tmp_path / "0.parquet")
    (tmp_path / "1.parquet").touch()  # what a Nextflow stub leaves
    frame(0).to_parquet(tmp_path / "2.parquet")  # a real patch over glass
    frame(1).to_parquet(tmp_path / "3.parquet")
    cells = read_patches([tmp_path / f"{i}.parquet" for i in range(4)])
    assert len(cells) == 3


def test_read_patches_all_empty_gives_empty_frame(tmp_path):
    (tmp_path / "0.parquet").touch()
    frame(0).to_parquet(tmp_path / "1.parquet")
    cells = read_patches([tmp_path / "0.parquet", tmp_path / "1.parquet"])
    assert len(cells) == 0
    with pytest.raises(ValueError, match="found no cells"):
        check_not_empty(cells, "x")


def test_store_image_key_reads_root_attributes(tmp_path):
    (tmp_path / "zarr.json").write_text(
        json.dumps({"zarr_format": 3, "node_type": "group", "attributes": {"cell_segmentation_image": "img"}})
    )
    assert store_image_key(tmp_path) == "img"


def test_store_image_key_missing_names_attribute(tmp_path):
    (tmp_path / "zarr.json").write_text('{"zarr_format": 3, "node_type": "group", "attributes": {}}')
    with pytest.raises(ValueError, match="cell_segmentation_image"):
        store_image_key(tmp_path)
