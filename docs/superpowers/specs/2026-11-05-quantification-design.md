# 3.0: quantification beyond the mean, and cell morphology

Replaces ROADMAP 2.1 item 1. Breaking: the table's `var` and `obs.area` change, hence 3.0.

## Goal

Each cell table carries the per-marker statistics and shape features that phenotyping and QC
need, for the whole cell and each compartment, from the existing `AGGREGATE` task.

Success: pytest passes, including mean equality with 2.0 and tile-size invariance; stub
nf-tests pass; on exemplar-001 and exemplar-002 the `*_mean` columns match 2.0's table and the
QC reports render as before.

## Findings that shape the design

- **No benchmark compares mean, median and quantiles for phenotyping.** The mean is every
  tool's default and a strong baseline (Gerber et al. 2025, bioRxiv). Median and quartiles are
  the usual extras (MCQuant, CellProfiler, QuPath).
- **q99 is the max for small cells**: in a 50 px cell it is the 49th of 50 sorted pixels. Min
  is mostly background, max mostly hot pixels or a bright neighbour. QC signals, not defaults.
- **Medians and SDs need all of a cell's pixels at once.** The 2.0 loop sums per dask chunk, so
  a cell crossing a chunk edge is never whole in memory.
- **Morphology is a weak but orthogonal signal in tissue** (Tamir et al. 2026; Mesmer's N/C
  ratio). Every feature below is exact on polygons; no raster needed.
- **Circularity depends on how the polygon was made** (sopa smooths) and is unstable below
  ~30 px². Compare it within one method only.
- **scverse/mantispy computes no morphology**; it profiles CellProfiler output.

## Parameter

`quantification_statistics`, string, default `"mean,median,std"`. Menu: `mean`, `median`,
`std`, `min`, `max`, `q25`, `q75`, `q90`. The schema `pattern` rejects anything off the menu;
`validateParams` requires `mean` (QC clusters on it) and rejects duplicates, each with its own
message. `conf/modules.config` passes it to `AGGREGATE` as `--statistics`.

## The table

`{method}_table`, one row per cell, or per nucleus in a nuclei-only run.

- `X`: statistics over the measured shape (expanded if `expand_radius_ratio` is set), float32.
  `var_names` are `{marker}_{statistic}` (`CD3_mean`), ordered statistic-major in the order
  requested; `var` has columns `marker` and `statistic`.
- `layers['nucleus']`, `layers['cytoplasm']`: the same `var` over each compartment, float32.
  Present when both targets ran, as in 2.0.
- NaN wherever the shape covers no pixel centre, as in 2.0.
- `obs`, from the unexpanded shapes, in px and px²:
  - `cell_area` (was `area`), `cell_perimeter`, `cell_circularity`, `cell_solidity`,
    `cell_eccentricity`, `cell_major_axis_length`, `cell_minor_axis_length`.
  - With linked nuclei, the same seven as `nucleus_*` over the nucleus compartment (the
    geometry `nucleus_area` already uses), plus `nc_ratio` = `nucleus_area / cell_area`, NaN
    without a nucleus.
  - In a nuclei-only run, the rows' own shape as `nucleus_*`; no `cell_*`.
  - Unchanged: `region`, `slide`, `core_id`, `cell_id`, `n_nuclei`, `nucleus_id`,
    `cytoplasm_area`.
- `uns['quantification']`: `statistics`, `tile_size`, and the largest read window.
- `uns['segmentation']` and `obsm['spatial']`: unchanged.

Definitions: `std` is the population SD (ddof 0); quantiles use numpy's default linear
interpolation. Circularity is 4πA/P², NaN below 30 px². Eccentricity and axis lengths come from
the polygon's second moments, as scikit-image's `regionprops` defines them. Solidity is area
over convex-hull area.

## Computation

`bin/aggregate_compartments.py`:

- `measure_intensities(image, shapes, statistics, tile_size=2048)` replaces `mean_intensities`
  and returns `(n_shapes, n_markers × n_statistics)`.
- Each shape belongs to the tile holding its centroid. A tile's read window is the tile grown
  to cover its own shapes' pixel bounds, so one giant shape enlarges only its own window.
- Each window is read once. Per shape, the hole-aware `rasterize` (unchanged; MultiPolygon
  parts OR-ed) selects its pixels as `(n_px, n_markers)`; each statistic is one numpy call.
- Sequential: no shared arrays across tasks, so the `synchronous` workaround goes. The 2.0
  chunk-edge mask fix is moot, as shapes no longer straddle reads.
- Results do not depend on `tile_size`. It stays a script constant, not a pipeline parameter.

New `bin/measure_shapes.py`, pure functions imported by the aggregate script:

- `shape_features(geoms, prefix) -> DataFrame` with the seven columns.
- Second moments by Green's theorem over each ring: exterior added, holes subtracted,
  MultiPolygon parts summed.

`QC_METRICS` and `QC_IMAGES` select `var.statistic == "mean"` and take marker names from
`var.marker`. The module's inputs, outputs and stub are unchanged.

## Tests

pytest, in `tests/unit/`:

- The 2.0 mean tests, ported to `measure_intensities`; their hand-computed values anchor the
  mean to 2.0.
- Tile-size invariance: tiny tiles, forcing many shapes across tile edges, equal one tile.
- Each statistic against numpy on a known shape; NaN for an empty mask.
- Shape features against `regionprops` on rasterised discs and ellipses (tolerance); a ring
  with a hole; a MultiPolygon; circularity NaN on a tiny shape; `nc_ratio` NaN without nucleus.
- QC on a 3.0-layout table.

nf-test: the existing stub tests; a validation test for `quantification_statistics` without
`mean` and with an off-menu value. Before release, the exemplar runs check the means against 2.0.

## Docs and release

- `docs/output.md`: the table section, a snippet to select a statistic, and a migration note
  (`area` → `cell_area`; `adata[:, "CD3"]` → `adata[:, "CD3_mean"]`).
- `docs/decisions.md`: a Quantification entry (read windows, not segmentation patches; the
  statistic menu; polygon morphology; pixel units).
- `CHANGELOG.md`: breaking changes for 3.0.0.
- `ROADMAP.md`: drop 2.1 item 1; rename the release heading to 3.0.
- No new tool in `CITATIONS.md`; no graph change, so no metro re-render.

## Out of scope

Cell filtering (2.1 item 2), the QC report chapter for these features (item 3), µm units,
parallel tiles (a follow-up if the exemplar runs are slow), membrane-ring compartments.
