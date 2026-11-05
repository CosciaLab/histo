# 3.0 Quantification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each cell table carries mean, median and SD (and optional extras) per marker for the
cell and its compartments, plus polygon morphology in `obs`.

**Architecture:** `AGGREGATE` keeps its inputs and outputs. Inside, `measure_intensities` reads
the image in tile windows grown to cover each tile's own shapes, so every shape is measured
whole once. A new pure module, `bin/measure_shapes.py`, computes shape features from polygons.
QC reads the mean columns by `var.statistic`.

**Tech Stack:** Python (numpy, shapely, geopandas, xarray/dask, anndata, spatialdata), pytest
via `uv run --frozen --group dev`, Nextflow DSL2, nf-test, nf-schema. Container unchanged:
`docker.io/josenimo/sopa:2.2.12`.

**Spec:** `docs/superpowers/specs/2026-11-05-quantification-design.md`. Read it first.

## Global Constraints

- Read CLAUDE.md. Branch `feat/quantification`; never push. Commit titles under ~60 chars,
  ending with the `Co-Authored-By` line.
- Statistic menu, in this spelling: `mean`, `median`, `std`, `min`, `max`, `q25`, `q75`, `q90`.
  Default `mean,median,std`. `mean` is required.
- `var_names` = `{marker}_{statistic}`, statistic-major in the order requested; `var` columns
  `marker`, `statistic`. Never parse `var_names`; marker names may contain `_`.
- `X` and layers are float32; compute in float64, cast at the end. `std` uses ddof 0; quantiles
  numpy's default (`linear`).
- `obs` morphology columns, in px/px²: `{p}_area`, `{p}_perimeter`, `{p}_circularity`,
  `{p}_solidity`, `{p}_eccentricity`, `{p}_major_axis_length`, `{p}_minor_axis_length`, `p` in
  `cell`, `nucleus`. `MIN_CIRCULARITY_AREA = 30.0` px². `nc_ratio` NaN when `n_nuclei == 0`.
- `TILE_SIZE = 2048`, a script constant.
- `bin/` scripts import heavy libraries inside functions. No `tifffile.imread` in `bin/` (hook).
- Edit `nextflow_schema.json` by hand; never `assets/params_template*.yml` (a hook regenerates).
- Run before each commit: `prek`, `uv run --frozen --group dev pytest tests/unit`,
  `nf-test test --tag stub,validation` (the last from Task 5 on).

## Review Focus

1. **A shape touching or crossing the image edge**, its centroid on the last pixel row: measured
   from in-image pixels only, no index error. Test in Task 2.
2. **One shape much larger than a tile** (a merged blob): measured whole, same values as with one
   big tile. Test in Task 2.
3. **Marker names containing `_`** (`CD45_RO`): `var.marker`/`var.statistic` correct and QC
   selects the right columns. Tests in Tasks 3 and 4.
4. **Missing or empty geometry** (`None`, empty polygon): NaN intensities and NaN morphology,
   no crash. Tests in Tasks 1 and 2.
5. **QC handed a 2.x-layout table** (no `var.statistic`): fails naming the missing column and
   saying the table predates 3.0. Test in Task 4.

---

### Task 1: Shape features from polygons

**Files:**

- Create: `bin/measure_shapes.py`
- Test: `tests/unit/test_measure_shapes.py`

**Interfaces:**

- Produces: `MIN_CIRCULARITY_AREA = 30.0`;
  `shape_features(geoms: Sequence[BaseGeometry | None], index: pd.Index, prefix: str) -> pd.DataFrame`,
  indexed by `index`, the seven columns of Global Constraints, float64.

- [ ] **Step 1: Write the failing tests**

```python
def ellipse(a, b, x=100.0, y=200.0):
    return shapely.affinity.translate(shapely.affinity.scale(Point(0, 0).buffer(1, quad_segs=256), a, b), x, y)

def test_ellipse_axes_and_eccentricity():
    f = shape_features([ellipse(20, 10)], pd.Index(["c0"]), "cell").iloc[0]
    assert f.cell_major_axis_length == pytest.approx(40, rel=1e-3)
    assert f.cell_minor_axis_length == pytest.approx(20, rel=1e-3)
    assert f.cell_eccentricity == pytest.approx(np.sqrt(1 - 0.25), rel=1e-3)

def test_rotation_does_not_change_axes(): ...   # rotate ellipse(20, 10) by 30°: same three values
def test_disc_circularity_near_one(): ...      # ellipse(10, 10): circularity ≈ 1 (rel 1e-3), eccentricity < 1e-3
def test_square_circularity_and_solidity():    # box(0,0,10,10): circularity == approx(pi/4), solidity == 1, perimeter == 40
def test_l_shape_solidity(): ...                # union of box(0,0,10,2) and box(0,0,2,10): solidity == area / hull area < 1
def test_hole_subtracted(): ...                 # box(0,0,20,20) minus box(5,5,15,15): area 300, eccentricity ≈ 0
def test_multipolygon_sums_parts(): ...         # box(0,0,4,4) and box(10,0,14,4): area 32, major > minor
def test_tiny_shape_circularity_nan(): ...      # box(0,0,5,5) (25 px²): circularity NaN, area 25
def test_none_and_empty_are_nan(): ...          # [None, Polygon()]: every column NaN
def test_prefix_and_index(): ...                # prefix "nucleus": columns start "nucleus_", index preserved
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --frozen --group dev pytest tests/unit/test_measure_shapes.py -v`
Expected: FAIL, `ModuleNotFoundError: measure_shapes`.

- [ ] **Step 3: Implement `shape_features` in `bin/measure_shapes.py`**

Module docstring: one paragraph, polygon-exact features, px units, definitions as in the spec.
Area, perimeter (`shapely.length`) and convex hull area vectorised with shapely; moments per
geometry. Second moments by Green's theorem, after `shapely.geometry.polygon.orient(p, 1.0)`
(exterior CCW, holes CW, so holes subtract) and translating by the geometry's bounds minimum
(precision at slide coordinates). For each ring, with `c_i = x_i y_{i+1} − x_{i+1} y_i`:

```text
A   = Σ c_i / 2
m10 = Σ c_i (x_i + x_{i+1}) / 6           m01 = Σ c_i (y_i + y_{i+1}) / 6
m20 = Σ c_i (x_i² + x_i x_{i+1} + x_{i+1}²) / 12
m02 = Σ c_i (y_i² + y_i y_{i+1} + y_{i+1}²) / 12
m11 = Σ c_i (x_i y_{i+1} + 2 x_i y_i + 2 x_{i+1} y_{i+1} + x_{i+1} y_i) / 24
```

Sum over all rings of all parts; central `mu20 = m20/A − cx²`, `mu02`, `mu11 = m11/A − cx·cy`.
Eigenvalues `l1 ≥ l2` of `[[mu20, mu11], [mu11, mu02]]`: major `4√l1`, minor `4√l2`,
eccentricity `√(1 − l2/l1)` (0 when `l1 == 0`), as skimage defines them. Circularity
`4πA/P²`, NaN where `A < MIN_CIRCULARITY_AREA`. NaN rows for `None`/empty.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --frozen --group dev pytest tests/unit/test_measure_shapes.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit** `Add polygon shape features` (both files).

---

### Task 2: Tiled intensity statistics

**Files:**

- Modify: `bin/aggregate_compartments.py` (replace `mean_intensities`, `compartment_layer`;
  module docstring)
- Test: `tests/unit/test_aggregate_compartments.py` (`TestMeanIntensities`,
  `TestCompartmentLayer`, `TestChunkEdges`)

**Interfaces:**

- Consumes: `rasterize`, `pixel_outer_bounds` (unchanged).
- Produces:
  - `STATISTICS: tuple[str, ...] = ("mean", "median", "std", "min", "max", "q25", "q75", "q90")`
  - `TILE_SIZE = 2048`
  - `parse_statistics(text: str) -> list[str]`: comma-separated, stripped; `ValueError` naming
    the problem for off-menu, duplicate, or missing `mean`.
  - `measure_intensities(image, shapes: gpd.GeoDataFrame, statistics: list[str], tile_size: int = TILE_SIZE) -> tuple[np.ndarray, int]`:
    float32 `(n_shapes, n_markers * n_statistics)`, statistic-major; and the largest read
    window side in px.
  - `compartment_layer(image, shapes, cells, statistics, tile_size=TILE_SIZE) -> tuple[np.ndarray, int]`:
    rows aligned to `cells`, NaN where absent.

- [ ] **Step 1: Port and add tests**

Rename every `mean_intensities(img, shapes)` call in the three classes to
`measure_intensities(img, shapes, ["mean"])[0]` and every `compartment_layer(...)` call to
`compartment_layer(..., ["mean"])[0]`, values unchanged (they anchor 2.0's mean).
Rename `TestChunkEdges` to `TestTiles`; its chunked case becomes `tile_size=16` against the
default. Add:

```python
def test_statistics_on_known_pixels():
    # 1-channel 3x3 cell over values 1..9, statistics in menu order
    img = make_image([np.arange(1, 10, dtype=float).reshape(3, 3)])
    out, _ = measure_intensities(img, frame([box(0, 0, 2, 2)]), list(STATISTICS))
    px = np.arange(1, 10, dtype=float)
    np.testing.assert_allclose(out[0], [px.mean(), np.median(px), px.std(), 1, 9,
                                        *np.quantile(px, [0.25, 0.75, 0.9])], rtol=1e-6)

def test_statistic_major_order(): ...   # 2 channels, ["mean", "std"]: columns [ch0_mean, ch1_mean, ch0_std, ch1_std]
def test_float32(): ...                 # out.dtype == np.float32
def test_tile_size_invariance(): ...    # position_image(), round cell, two-part, ring, a 30x30 blob, overlapping pair:
                                        # tile_size 8 equals tile_size 4096 for all statistics (assert_array_equal)
def test_edge_shape_inside_image_only(): ...  # box(30, 30, 45, 45) on a 40x40 image and centroid near 39.9: no error,
                                              # mean over the 10x10 in-image pixels (Review Focus 1)
def test_blob_larger_than_tile(): ...   # box(1, 1, 38, 38), tile_size 4: equals tile_size 4096 (Review Focus 2)
def test_none_and_empty_rows_nan(): ... # [None, Polygon(), box(0,0,4,4)]: rows 0-1 NaN, row 2 finite (Review Focus 4)
def test_window_reported(): ...         # box(1,1,38,38), tile_size 4: second return value >= 38

class TestParseStatistics:
    def test_default(self): assert parse_statistics("mean,median,std") == ["mean", "median", "std"]
    def test_spaces_stripped(self): ...           # " mean , q90" -> ["mean", "q90"]
    def test_off_menu(self): ...                   # "mean,q99": ValueError mentioning "q99" and the menu
    def test_duplicate(self): ...                  # "mean,mean": ValueError mentioning "mean"
    def test_mean_required(self): ...              # "median": ValueError mentioning "mean"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --frozen --group dev pytest tests/unit/test_aggregate_compartments.py -v`
Expected: FAIL on import of `measure_intensities`, `STATISTICS`, `parse_statistics`.

- [ ] **Step 3: Implement**

Image is `(c, y, x)` dask-backed. Owner tile per shape: `floor(centroid / tile_size)`, clipped
to the grid. Per tile: owned shapes' `pixel_outer_bounds` clipped to the image; window = union
of the tile rectangle and those bounds; read once with `image.data[:, y0:y1, x0:x1].compute()`.
Per shape: slice its bounds from the window, `rasterize(cell, sub.shape[1:], (bx0, by0))`,
pixels `sub[:, mask.astype(bool)].T.astype(np.float64)`; empty mask, `None` or empty geometry
→ NaN row. Each statistic is one numpy reduction along axis 0. Drop the dask `delayed`
machinery and the synchronous-scheduler comment. Keep the sopa licence header and update the
"copied from" note: the loop is now ours; `rasterize` and `pixel_outer_bounds` stay from sopa.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --frozen --group dev pytest tests/unit/test_aggregate_compartments.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit** `Measure statistics per cell in tile windows`.

---

### Task 3: Table layout, morphology and CLI

**Files:**

- Modify: `bin/aggregate_compartments.py` (`build_table`, `parse_args`, `main`, new `stat_var`)
- Test: `tests/unit/test_aggregate_compartments.py` (`TestBuildTable`, new `TestStatVar`,
  `TestObsColumns`)

**Interfaces:**

- Consumes: Task 1 `shape_features`; Task 2 `measure_intensities`, `compartment_layer`,
  `parse_statistics`, `TILE_SIZE`.
- Produces:
  - `stat_var(markers: list[str], statistics: list[str]) -> pd.DataFrame`: index
    `{marker}_{statistic}`, columns `marker`, `statistic`, statistic-major.
  - `obs_columns(cells, target, nucleus_compartment, links) -> pd.DataFrame`: morphology plus
    links, indexed like `cells`. `target == "cells"`: `cell_*`; with links also `nucleus_*`
    (six from `shape_features` of the compartment reindexed to `cells`, plus `nucleus_area`
    from links, unchanged, 0 without a nucleus) and `nc_ratio`. `target == "nuclei"`:
    `nucleus_*` only.
  - `build_table(cells, x, var, layers, obs_extra, region, slide, core_id, specs, quantification: dict)`:
    `var` is a DataFrame; no `area` column of its own; `uns["quantification"] = quantification`.
  - CLI: `--statistics` (default `mean,median,std`, through `parse_statistics`; error via
    `parser.error`).

- [ ] **Step 1: Write the failing tests**

```python
def test_stat_var_marker_with_underscore():
    v = stat_var(["DAPI", "CD45_RO"], ["mean", "std"])
    assert list(v.index) == ["DAPI_mean", "CD45_RO_mean", "DAPI_std", "CD45_RO_std"]
    assert list(v["marker"]) == ["DAPI", "CD45_RO", "DAPI", "CD45_RO"]
    assert list(v["statistic"]) == ["mean", "mean", "std", "std"]
```

- `TestBuildTable`: the helper passes `var=stat_var(["DAPI", "CD3"], ["mean"])` and
  `quantification={"statistics": ["mean"], "tile_size": 2048, "max_window_px": 10}`;
  `test_obs_names_are_cell_index` asserts `var_names == ["DAPI_mean", "CD3_mean"]`;
  `test_sopa_obs_columns` drops the `area` assertion and asserts `"area" not in t.obs`;
  new `test_uns_quantification` asserts the dict round-trips; new `test_x_float32`.
- `TestObsColumns`:
  - `test_cells_only`: columns are exactly the seven `cell_*`; `cell_area` of `box(0,0,4,4)` is 16.
  - `test_with_links`: a cell with a nucleus gets finite `nucleus_eccentricity` and
    `nc_ratio == nucleus_area / cell_area`; a cell with `n_nuclei == 0` keeps `nucleus_area == 0`
    and has NaN `nc_ratio` and NaN `nucleus_circularity`.
  - `test_nuclei_only`: only `nucleus_*`; no `cell_*`, no `nc_ratio`.
- `test_parse_args_rejects_bad_statistics`: `parse_args([... "--statistics", "median"])` raises
  `SystemExit`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --frozen --group dev pytest tests/unit/test_aggregate_compartments.py -v`
Expected: FAIL on `stat_var`, `obs_columns`, `quantification`.

- [ ] **Step 3: Implement**

In `main`: `statistics = parse_statistics(args.statistics)`; X from the expanded shapes; layers
via `compartment_layer`; `obs_extra = obs_columns(cells, args.target, nucleus parquet or None,
links or None)`; `quantification = {"statistics": statistics, "tile_size": TILE_SIZE,
"max_window_px": max over X and layers}`. Morphology always from the unexpanded `cells`. Update
the `--expand-radius-ratio` help ("statistics", not "mean") and the final print to list the
statistics.

- [ ] **Step 4: Run all unit tests**

Run: `uv run --frozen --group dev pytest tests/unit -q`
Expected: all PASS except QC store tests that read `obs/area` (fixed in Task 4).

- [ ] **Step 5: Commit** `Write statistics to var and morphology to obs`.

---

### Task 4: QC reads the 3.0 table

**Files:**

- Modify: `bin/qc_metrics.py:478-481,595`, `bin/qc_images.py:673,730`
- Test: `tests/unit/qc/test_qc_metrics_store.py` (`make_table` fixture and new tests)

**Interfaces:**

- Produces, in `bin/qc_metrics.py`:
  - `mean_columns(table) -> tuple[list[str], list[int]]`: marker names and `X` column indices
    where `var/statistic == "mean"`, in `var` order. Missing `var/statistic` or `var/marker`:
    `ValueError` naming the column and "written before 3.0".
  - `row_areas(table) -> np.ndarray`: `obs/cell_area`, else `obs/nucleus_area` (nuclei-only).
- `qc_images.py` imports both from `qc_metrics`, as it does `read_column`.

- [ ] **Step 1: Update the fixture and write failing tests**

`make_table` writes `obs/cell_area` instead of `obs/area`, `var/_index` as
`{name}_mean` then `{name}_median`, categorical `var/marker` and `var/statistic`, and `X` with
two statistics so a wrong column choice changes the result. Add:

- `test_mean_columns_select_means`: markers equal the fixture's channel names; indices `0..n-1`.
- `test_mean_columns_marker_with_underscore`: a `CD45_RO` channel round-trips (Review Focus 3).
- `test_real_anndata_table`: `build_table(...)` from `aggregate_compartments`, written with
  `write_zarr` to `store/tables/t`, then `mean_columns` and `row_areas` read it; guards the
  fixture against drifting from anndata's real encoding.
- `test_2x_table_refused`: a table without `var/statistic` raises `ValueError` matching
  `"before 3.0"` (Review Focus 5).
- `test_nuclei_only_areas`: only `obs/nucleus_area` → `row_areas` returns it.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --frozen --group dev pytest tests/unit/qc -v`
Expected: FAIL on `mean_columns`, `row_areas`.

- [ ] **Step 3: Implement**

`channel_names, mean_cols = mean_columns(table)` replaces the `var/_index` read in both
scripts; `areas = row_areas(table)`; `X` reads become `table["X"].oindex[:, mean_cols]`. Update
the "X is sopa's per-cell mean intensity" comment.

- [ ] **Step 4: Run all unit tests**

Run: `uv run --frozen --group dev pytest tests/unit -q`
Expected: all PASS.

- [ ] **Step 5: Commit** `Read mean columns by statistic in QC`.

---

### Task 5: Pipeline parameter

**Files:**

- Modify: `nextflow_schema.json` (group `aggregation`), `nextflow.config:91-92`,
  `conf/modules.config:80-82`, `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`
  (`validateParams`)
- Test: `tests/validate_params.nf.test`

**Interfaces:**

- Consumes: the menu and the `--statistics` flag from Task 2/3.
- Produces: `params.quantification_statistics` (string, default `'mean,median,std'`).

- [ ] **Step 1: Write the failing nf-tests** (same style as the file's existing tests)

- `"default statistics are accepted"`: `[use_cellpose: true, quantification_statistics: 'mean,median,std']` → success.
- `"statistics without mean are rejected"`: `'median,std'` → failed; stdout contains
  `"quantification_statistics must include mean"`.
- `"duplicate statistics are rejected"`: `'mean,mean'` → failed; stdout contains
  `"quantification_statistics lists mean twice"`.

- [ ] **Step 2: Run to verify they fail**

Run: `nf-test test tests/validate_params.nf.test`
Expected: the two rejection tests FAIL.

- [ ] **Step 3: Implement**

- Schema property in `aggregation`: `type: string`, `default: "mean,median,std"`,
  `pattern: "^(mean|median|std|min|max|q25|q75|q90)(,(mean|median|std|min|max|q25|q75|q90))*$"`,
  description "Per-marker statistics, comma-separated, no spaces: mean, median, std, min, max,
  q25, q75, q90. mean is required." Group description becomes "Per-cell marker statistics and
  morphology". Update `expand_radius_ratio`'s description: "when measuring channel
  intensities", not "averaging".
- `nextflow.config`: `quantification_statistics = 'mean,median,std'` under the aggregation
  comment.
- `validateParams`: when `params.quantification_statistics != null`, split on `,`; assert
  `mean` present ("quantification_statistics must include mean: QC clusters on it. Got: …")
  and no duplicates ("quantification_statistics lists X twice"). One-line "why" comment.
- `conf/modules.config`: `ext.args` joins the existing expand arg and
  `"--statistics ${params.quantification_statistics}"`.

- [ ] **Step 4: Verify**

Run: `prek run --all-files && nf-test test --tag stub,validation`
Expected: hooks pass (params templates regenerated by the hook; stage them); all tests PASS.
Also `nextflow run . -profile test,laptop -stub --outdir /tmp/... --quantification_statistics median`
stops at startup naming the rule, and `--quantification_statistics mean,q99` stops at schema
validation.

- [ ] **Step 5: Commit** `Add quantification_statistics parameter` (include regenerated templates).

---

### Task 6: Docs and changelog

**Files:**

- Modify: `docs/output.md:146-175`, `docs/decisions.md` (new `## Quantification` after
  `## Segmentation`; trim the aggregation paragraph at `:132` to what still holds),
  `CHANGELOG.md`, `ROADMAP.md`

- [ ] **Step 1: Write**

- `output.md`: `X`, layers and `obs` as in the spec's "The table"; the `area` row of the NaN
  table becomes `cell_area`; a 3-line snippet:
  `adata[:, adata.var.statistic == "median"]`; a "From 2.x" note
  (`area` → `cell_area`; `adata[:, "CD3"]` → `adata[:, "CD3_mean"]`; float32).
- `decisions.md`: four short paragraphs: read windows, not segmentation patches (size tuned for
  segmentation; overlap not guaranteed; coupling); the menu and why not q99/min/max by default;
  morphology on polygons, circularity comparable within one method; pixel units.
- `CHANGELOG.md`: `## v3.0.0 - [unreleased]` with `### Breaking` (var layout, `area` →
  `cell_area`, float32, QC needs a 3.0 table) and `### Added` (statistics parameter, morphology,
  `nc_ratio`, `uns['quantification']`).
- `ROADMAP.md`: remove 2.1 item 1, renumber; rename "2.1" to "3.0" where it names this release.

- [ ] **Step 2: Verify**

Run: `prek run --all-files`
Expected: PASS (prettier may reformat; restage).

- [ ] **Step 3: Commit** `Document 3.0 table layout and quantification`.

---

### Task 7: Full verification

- [ ] **Step 1: Every local tier**

Run: `prek run --all-files && nf-core pipelines lint && uv run --frozen --group dev pytest tests/unit -q && nf-test test --tag stub,validation`
Expected: all PASS; lint warnings no worse than on `dev`.

- [ ] **Step 2: Container smoke test (Mac, Docker)**

In `docker.io/josenimo/sopa:2.2.12` (`--platform linux/amd64`, repo mounted), run a scratchpad
script that imports `measure_shapes` and `aggregate_compartments` from `bin/` and calls
`shape_features` and `measure_intensities` on a 40×40 two-channel array with three boxes.
Expected: no import or numpy/shapely API error. This checks the container's library versions,
not tool behaviour.

- [ ] **Step 3: Propose the cluster runs to the user** (never submit)

The exemplar-001 and exemplar-002 commands from `docs/CONTRIBUTING.md`, plus a short Python
check comparing each table's `*_mean` columns with the 2.0 table at `rtol=1e-6`, and noting `AGGREGATE`'s time
and peak memory against 2.0.
