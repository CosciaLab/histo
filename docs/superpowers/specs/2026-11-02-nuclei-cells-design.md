# 2.0: nuclei and cells, linked; methods side by side

Replaces ROADMAP 1.5. Breaking: output names change and StarDist is removed, hence 2.0.

## Goal

One run segments nuclei and whole cells, derives the cytoplasm, links each nucleus to its cell
and quantifies all three compartments. Separately, Cellpose and InstanSeg can run on the same
image as a second opinion. Each segmentation is independent, so a new method is one more entry.

Success: the four stub combinations below pass; exemplar-001 (both methods, both targets) and
exemplar-002 (TMA, InstanSeg nuclei and cells) give one table per method with compartment
layers, and QC shows link counts and the comparison.

Typical runs: InstanSeg nuclei + cells; InstanSeg cells + Cellpose cells. Exhaustive: both
methods, both targets, two tables.

## Findings that shape the design

- **sopa's segmentation CLI has no `--image-key`.** It segments the image named by the store
  attribute `cell_segmentation_image`, which `PROJECT_CHANNELS` flips today. Two methods on two
  images cannot share that attribute. The Python `StainingSegmentation(..., image_key=)` can.
- **sopa's `rasterize` ignores holes** (`sopa/shapes/_rasterize.py:32-35`, exterior only). A
  cytoplasm ring would be measured as the whole cell.
- **`sopa resolve` and `sopa aggregate` write into the store.** Parallel writers race on root
  `zmetadata` and `.zattrs`; last writer wins, silently.
- **sopa's `parse_table` renumbers shape indices** at aggregation, which would break links.
- **InstanSeg through sopa returns one `--target`.** Nuclei and cells are two passes.

## Parameters

Schema via `nf-core pipelines schema build` only.

- `use_cellpose`, `use_instanseg`: methods. No longer exclusive; at least one.
- `segment_cells` (default `true`), `segment_nuclei` (default `false`): targets; at least one.
  Both on derives cytoplasm.
- Removed: `use_stardist` and every `stardist_*`, `instanseg_target` (replaced by the targets).
  Setting any fails at startup with "removed in 2.0".
- Other `cellpose_*` and `instanseg_*` params apply to both targets of their method.
- `use_gpu` applies to Cellpose specs only; InstanSeg stays on CPU and says so in the log.
  Lift once sopa calls `.cpu()` (ROADMAP, Known limitations).

## Segmentation specs

At startup, methods × targets become a list of Groovy maps, one per segmentation:

```groovy
[name: 'instanseg_nuclei', method: 'instanseg', target: 'nuclei',
 image: '<image>', channels: [...], args: '...', memory_gb: 12]
```

- Cellpose cells: `<image>_projected` with `['cell', 'nuclear']` when `use_projection`, else
  `cellpose_channels`. Cellpose nuclei: the nuclear channel only, from the same image.
- InstanSeg: the full image; channels from `instanseg_channels`, else
  `defaultInstansegChannels(sheet, target)`. `memory_gb` per spec, as channel counts differ.
- `cellpose_kwargs` / `instanseg_kwargs` stay text, as `method_kwargs_extra: "<string>"`;
  `segment_patch.py` parses it with `ast.literal_eval`, merges it into `method_kwargs`, and fails
  naming any key a dedicated parameter already sets.
- The maps are written to each table's `uns["segmentation"]`.

## Graph

✎ marks a task that writes the store.

```
TO_SPATIALDATA ✎ → SET_CHANNEL_NAMES ✎ → TISSUE_SEGMENTATION ✎
→ PROJECT_CHANNELS ✎    adds <image>_projected; the attribute stays on the full image
→ MAKE_IMAGE_PATCHES ✎  once; one grid and ROI for every spec
→ SEGMENT_PATCH         spec × patch → {index}.parquet
→ RESOLVE               per spec → {spec}.parquet
→ LINK_COMPARTMENTS     per method, when both targets → cells, nuclei, cytoplasm parquets
→ AGGREGATE             per method → {method}_table.h5ad
→ WRITE_SEGMENTATIONS ✎ per sample, the only writer: shapes, tables; drops the projection
→ QC per table, COMPARE_SEGMENTATIONS per sample → MERGE_SPATIALDATA (TMA) → PUBLISH
```

- `SEGMENT_PATCH`: `bin/segment_patch.py`, about 20 lines over `StainingSegmentation` and
  `write_patch_cells`, with an explicit `image_key`. Offer `--image-key` to sopa upstream; drop
  the script once released.
- `RESOLVE`: sopa's `read_patches_cells` and `solve_conflicts`, written to GeoParquet. Sets the
  index once: `{image_key}_{target}_{n}`, unique per store and across TMA cores.
- `AGGREGATE`: reads the image read-only. Sets `obs/slide` and `obs/core_id` directly, which
  replaces `bin/set_cell_metadata.py`. Builds the table with `TableModel.parse`, not sopa's
  `parse_table`, so indices are kept.
- `WRITE_SEGMENTATIONS`: re-reads the store and checks every expected element and table.
- Removed: `CELLPOSE`, `INSTANSEG`, `STARDIST` subworkflows, their six modules, and
  `DROP_PROJECTION` (folded into the writer). `keep_projection` keeps its meaning.
- One generic set of modules on `docker.io/josenimo/sopa:2.2.12`; no new image.

## Store layout

Per method `m`:

| Element         | When             | Content                                                 |
| --------------- | ---------------- | ------------------------------------------------------- |
| `{m}_cells`     | `segment_cells`  | resolved cell polygons                                  |
| `{m}_nuclei`    | `segment_nuclei` | resolved nucleus polygons; `cell_id`, empty if unlinked |
| `{m}_cytoplasm` | both             | cell minus its nucleus compartment; same index as cells |
| `{m}_table`     | always           | one row per cell (per nucleus in a nuclei-only run)     |

Table: `X` whole-cell mean (nucleus mean in a nuclei-only run); `layers["nucleus"]`,
`layers["cytoplasm"]` when both targets. `obs`: sopa's `region`, `cell_id`, `area`, `slide`;
plus `nucleus_area`, `cytoplasm_area`, `n_nuclei`, `nucleus_id` (largest linked nucleus).
`region` is `{m}_cells`, or `{m}_nuclei` in a nuclei-only run.

## Linking rules

`bin/link_compartments.py`, per method:

1. A nucleus links to the cell holding the largest share of its area, if that share is ≥ 0.5.
   A constant with a one-line why, not a param.
2. A cell's nucleus compartment is the union of its linked nuclei, clipped to the cell.
3. Cytoplasm is the cell minus that union; it may be a ring or a multipolygon.
4. `n_nuclei = 0`: `nucleus` and `cytoplasm` layers are NaN.
5. Empty cytoplasm: its layer is NaN, `cytoplasm_area` 0.
6. Nothing is dropped. Unlinked nuclei stay in `{m}_nuclei`.

The nucleus compartment is measured, not stored; the raw nuclei are stored.

## Aggregation

`bin/aggregate_compartments.py` copies sopa's `_aggregate_channels_aligned` and `rasterize`,
keeping sopa's licence header and source commit. One change: holes are rasterized as 0. Mean
per compartment, as today. ROADMAP's later "aggregation beyond the mean" extends this script.
Offer the hole fix to sopa upstream.

## QC and comparison

- `QC` runs per sample × method on `{m}_table`; `{sample}_{m}_qc.json`, one report chapter per
  method. With nuclei: distribution of `n_nuclei`, unlinked nuclei, empty-cytoplasm cells.
- `COMPARE_SEGMENTATIONS`, only when both methods ran with `segment_cells`: cell counts, median
  areas, share of cells matched one-to-one at IoU ≥ 0.5 in each direction, both outlines on
  the same 3 crops. One report chapter.
- `qc_metrics.py` and `qc_images.py` take the table name instead of reading `tables/table`.

## Errors

- Startup, with `error()`: the two "at least one" rules; removed params; `use_projection`
  without `use_cellpose`.
- A spec that resolves to 0 cells fails, naming the spec.
- Linking checks one table row per cell and unique indices.
- `MERGE_SPATIALDATA` retargets every table per core; test with several tables per core.

## Testing

Spikes first, throwaway, local `uv`, exemplar-001 one-patch crop:

1. `segment_patch.py` with two `image_key`s gives two distinct parquets.
2. Hole-aware aggregation of a synthetic ring gives the ring's mean, not the cell's.

Then:

- pytest: spec builder; linking rules 1–6 on hand-drawn polygons; ring aggregation; table
  assembly; merge with several tables.
- nf-test: a stub for every new module. Workflow stubs: Cellpose cells; InstanSeg nuclei +
  cells; Cellpose cells + InstanSeg cells; both methods, both targets. Update `args_cli`,
  `exemplar001.nf.test` (`shapes/cellpose_cells`).
- Cluster: exemplar-001 exhaustive, exemplar-002 InstanSeg nuclei + cells. New ±2% baselines.

## Commits, in order

Each leaves a working pipeline.

1. Remove StarDist.
2. Spec builder, `SEGMENT_PATCH`, `RESOLVE`, `AGGREGATE`, `WRITE_SEGMENTATIONS`; one method,
   cells only. Output names change here.
3. Both methods together; `use_gpu` for Cellpose only.
4. `segment_nuclei`, `LINK_COMPARTMENTS`, hole-aware aggregation with layers.
5. QC per table, `COMPARE_SEGMENTATIONS`.
6. Docs: `output.md` with a 1.x → 2.0 migration note, `usage.md`, `decisions.md`, metro map
   (rendered and checked by eye), `CITATIONS.md` without StarDist, CHANGELOG, ROADMAP
   (this replaces 1.5; quantification and learned features follow; dearray-first moves to 3.0).

## Out of scope

- A segmentation sheet. The spec maps are its shape if sweeps ever need one.
- One InstanSeg pass for both targets. Only if two passes prove too slow.
- Area filtering, quantiles, morphology: the later quantification release.
