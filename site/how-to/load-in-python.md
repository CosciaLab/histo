# Load the results in Python

Goal: read a sample's cells, measurements and outlines from `{sample}.zarr`. The full layout is
in [SpatialData directory](../reference/output.md#spatialdata-directory).

## Steps

1. Install [spatialdata](https://spatialdata.scverse.org/en/stable/): `pip install spatialdata`.
2. Read the store and pick a method's table and shapes:

   ```python
   import spatialdata as sd

   sdata = sd.read_zarr("results/slide01.zarr")
   print(sdata)  # every image, shape and table

   adata = sdata.tables["cellpose_table"]  # one row per cell
   cells = sdata.shapes["cellpose_cells"]  # outlines, indexed by the same cell ids

   means = adata[:, adata.var["statistic"] == "mean"].to_df()  # cells × {marker}_mean
   cd3 = adata[:, "CD3_mean"].X
   adata.obs[["cell_area", "slide"]]
   nucleus = adata.layers["nucleus"]  # with segment_nuclei: same columns, over the nucleus
   outlines = cells.loc[adata.obs_names, "geometry"]
   ```

3. Pick the names for your run, with `{m}` the method, `cellpose` or `instanseg`:

   | Run                         | Table                  | Shapes                                     | Layers                 |
   | --------------------------- | ---------------------- | ------------------------------------------ | ---------------------- |
   | Cells                       | `{m}_table`            | `{m}_cells`                                | none                   |
   | Cells and nuclei            | `{m}_table`            | `{m}_cells`, `{m}_nuclei`, `{m}_cytoplasm` | `nucleus`, `cytoplasm` |
   | Nuclei only                 | `{m}_table`            | `{m}_nuclei`                               | none                   |
   | Dearrayed TMA, merged store | `{core_id}__{m}_table` | `{core_id}__{m}_cells`, …                  | as above               |

% source: docs/output.md#spatialdata-directory
% source: site/outputs/what-changes-it.md
% source: bin/aggregate_compartments.py:199-260
% source: bin/aggregate_compartments.py:345-372
% source: bin/write_segmentations.py:1-26
% source: snippet run on 2026-11-05 with spatialdata 0.8.0 against a store built with build_table

## Pitfalls

- **NaN is "not measured", 0 is "measured, nothing there"**, e.g. the layers of a cell without
  a nucleus. See the NaN table in [SpatialData directory](../reference/output.md#spatialdata-directory).
- **Select columns by `var["marker"]` and `var["statistic"]`**, not by parsing the names.
- **Ids repeat across stores.** Keep `slide` and `core_id` when you concatenate tables, and make
  `obs_names` unique.
- **A nuclei-only table** has `nucleus_*` columns and no `cell_*`.

% source: docs/output.md#spatialdata-directory
% source: bin/aggregate_compartments.py:200
