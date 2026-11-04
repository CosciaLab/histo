# 2.0 Nuclei and Cells Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One run segments nuclei and cells with Cellpose and/or InstanSeg, links them, and
quantifies cell, nucleus and cytoplasm into one table per method.

**Architecture:** Params become a list of segmentation spec maps. Patch, resolve, link and
aggregate tasks are pure (files in, files out, store read-only); one `WRITE_SEGMENTATIONS`
task per sample is the only writer. Aggregation is copied from sopa with holes honoured.

**Tech Stack:** Nextflow DSL2, nf-test, sopa 2.2.12 (`docker.io/josenimo/sopa:2.2.12`),
spatialdata, geopandas, shapely, scikit-image, pytest via `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-02-nuclei-cells-design.md`. Read it first.

## Global Constraints

- Read CLAUDE.md. Commit on a feature branch off `dev`; never push. Titles under ~60 chars.
- Schema only via `nf-core pipelines schema build`; never hand-edit `nextflow_schema.json` or
  `assets/params_template*.yml`.
- Every new local module: `main.nf` with a `stub:` that creates every output, `meta.yml`,
  `environment.yml`, `versions.yml`. Container `docker.io/josenimo/sopa:2.2.12` for every new
  module; no new image.
- Element names: `{m}_cells`, `{m}_nuclei`, `{m}_cytoplasm`, `{m}_table`, `m` in
  `cellpose`, `instanseg`.
- Shape index: `{image_key}_{target}_{n}`, `target` in `cells`, `nuclei`, `n` from 0.
- Link threshold: share ≥ 0.5 of the nucleus area inside the cell.
- Options left unset in params must reach sopa's method with sopa 2.2.12's CLI defaults
  (`sopa/cli/segmentation.py`; e.g. Cellpose `flow_threshold 2`, `cellprob_threshold -6`).
  Otherwise unchanged params silently segment differently.
- Python in `bin/` imports heavy libraries inside `main()` so pure functions test without them.
- Run before each commit: `prek`, `uv run pytest tests/unit`, `nf-test test --tag stub,validation`.
- `params` validation stays top-level `assert` with a message, as in `validateParams`; the
  `error()` lesson applies inside channel operators.

## Review Focus

1. **Unset params give sopa's defaults.** A run with no `flow_threshold` set must pass 2 to
   Cellpose, as 1.4 did. Test in Task 3.
2. **A patch with no cells.** Empty parquets are normal (glass, tissue edge); resolve must not
   fail on them, but a spec with 0 cells in total fails naming the spec. Test in Task 4.
3. **Retry or `-resume` meets an already-written store.** `WRITE_SEGMENTATIONS` replaces its
   elements; a second run on the same store gives the same elements. Test in Task 6.
4. **Ties and slivers in linking.** A nucleus split exactly 50/50 links to the lower cell
   index; `difference` may return a `GeometryCollection` with lines, of which only polygons
   are kept. Test in Task 10.
5. **A TMA core with cells but no nuclei.** Linking, aggregation and merge must accept an
   empty nuclei frame: all `n_nuclei` 0, layers NaN. Test in Task 10 and Task 11.

---

### Task 0: Spike: explicit image key per patch (throwaway)

Not committed. Answers: does `StainingSegmentation(..., image_key=)` read the named image when
the store attribute points elsewhere, and do sopa's `read_patches_cells` + `solve_conflicts`
work on parquets outside the store?

- [ ] **Step 1:** In the scratchpad, `uv run --with sopa==2.2.12 python spike.py`. The script
      builds a store with two 2-channel uint16 images of 512×512 (`img`, `img_projected`) that
      differ (bright disc at different places), sets `cell_segmentation_image` to `img`, runs
      `sopa.make_image_patches(sdata, 256, 20)`, then for each image key runs
      `StainingSegmentation(sdata, method, channels, image_key=k).write_patch_cells(dir_k, 0)`
      with `method = lambda img: skimage.measure.label(img[0] > threshold)`.
- [ ] **Step 2:** Expected: the two parquets hold polygons at different places. Then
      `solve_conflicts(StainingSegmentation.read_patches_cells([dir]))` returns a GeoDataFrame.
- [ ] **Step 3:** Report the result to the user. If `image_key` is ignored, stop: the design
      needs revisiting.

### Task 1: Remove StarDist; removed params stop the run

**Files:**

- Delete: `modules/local/patch_segmentation_stardist/`, `modules/local/resolve_stardist/`,
  `subworkflows/local/stardist/`
- Modify: `workflows/histo.nf` (include and `if (params.use_stardist)` block),
  `modules/local/utils.nf` (`stardist` group, `boundariesKey`), `nextflow.config`
  (stardist params), `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`
  (`validateParams` StarDist lines; `rejectUnknownParams` `deprecated`), `conf/sizes.config`
  (`RESOLVE_STARDIST` lines), `tools/container_manifest.py` / `containers.tsv` (via hook),
  `CITATIONS.md`, `README.md`, `docs/usage.md`, `docs/pipeline_paths.mmd`,
  `tests/args_cli.nf.test`
- Test: `tests/reject_unknown_params.nf.test`

**Interfaces:**

- Produces: `removed` map in `rejectUnknownParams`; any key in it stops the run.

- [ ] **Step 1: Write the failing tests** in `tests/reject_unknown_params.nf.test`:
      `use_stardist = true` fails, and stderr contains `use_stardist was removed in 2.0`;
      `technology = "ome_tif"` fails with `technology was removed in 2.0`.
- [ ] **Step 2:** `nf-test test tests/reject_unknown_params.nf.test` → new cases FAIL.
- [ ] **Step 3:** Replace `deprecated` with `removed`, a map from name to replacement text:
      `technology`, `aggregate_channels` (as today's texts), `use_stardist`,
      `stardist_model_type`, `prob_thresh`, `nms_thresh`, `stardist_channels`, `stardist_kwargs`
      (`'StarDist is no longer offered; use use_cellpose or use_instanseg'`). Fail with
      `"${name} was removed in 2.0 (${now})"` before the unknown-param check. Then delete the
      StarDist code, params (schema build), config and docs listed above.
- [ ] **Step 4:** `prek && nf-test test --tag stub,validation && uv run pytest tests/unit` →
      PASS. `grep -rni stardist --exclude-dir=.git .` lists only CHANGELOG and docs history.
- [ ] **Step 5:** Commit `Remove StarDist`.

### Task 2: Segmentation spec builder

**Files:**

- Modify: `modules/local/utils.nf`
- Test: `tests/segmentation_specs.nf.test` (new, `nextflow_function`, tag `validation`)

**Interfaces:**

- Produces: `def segmentationSpecs(Map args) -> List<Map>`, one map per enabled method ×
  target, in order cellpose-cells, cellpose-nuclei, instanseg-cells, instanseg-nuclei. Keys:
  - `name` (`"${method}_${target}"`), `method`, `target`
  - `image`: `'projected'` or `'full'`
  - `channels`: `List<String>`, or `null` for InstanSeg without `instanseg_channels` (filled
    per sample from the marker sheet in Task 8)
  - `method_kwargs`: `Map` of sopa method arguments, nulls removed
  - `segmentation_kwargs`: `Map` with `min_area`, `clip_limit`, `clahe_kernel_size`,
    `gaussian_sigma`, nulls removed
  - `gpu`: `true` only for Cellpose with `use_gpu`
- Produces: `def segmentationTargets(Map args) -> List<String>` from `segment_cells` and
  `segment_nuclei` (`args.segment_cells != false`, so it works before Task 8 adds the param).

- [ ] **Step 1: Write the failing tests**:
  - `use_cellpose`, cells, `cellpose_channels = 'CD45 DAPI'`: one spec, `image == 'full'`,
    `channels == ['CD45', 'DAPI']` (sopa's order: cytoplasm, then nucleus). Nuclei:
    `channels == ['DAPI']`.
  - `use_cellpose`, `use_projection`, both targets: cells has `['cell', 'nuclear']`, nuclei
    has `['nuclear']`, both `image == 'projected'`.
  - `use_instanseg`, nuclei: `method_kwargs.target == 'nuclei'`, `image == 'full'`,
    `channels == null` when `instanseg_channels` unset.
  - `use_gpu` with both methods: Cellpose `gpu == true`, InstanSeg `gpu == false`.
  - Cellpose `method_kwargs.diameter == 30`.
- [ ] **Step 2:** `nf-test test tests/segmentation_specs.nf.test` → FAIL (`segmentationSpecs`
      undefined).
- [ ] **Step 3:** Implement both functions in `utils.nf`, reusing `getChannels`. Cellpose
      nuclei without projection: the last name of `cellpose_channels`. Not wired yet.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `Add segmentation spec builder`.

### Task 3: SEGMENT_PATCH with an explicit image

**Files:**

- Create: `bin/segment_patch.py`, `modules/local/segment_patch/{main.nf,meta.yml,environment.yml}`
- Test: `tests/unit/test_segment_patch.py`

**Interfaces:**

- Consumes: a Task 2 spec, as JSON.
- Produces: `segment_patch.py --sdata S --spec spec.json --patch-index I --output I.parquet`.
  Pure functions: `image_key_for(attrs: dict, image: str) -> str` (`'full'` → the
  `cell_segmentation_image` attribute; `'projected'` → that plus `_projected`), and
  `method_arguments(spec: dict) -> dict` (spec `method_kwargs` over sopa 2.2.12's CLI
  defaults for that method, plus `channels`).
- Produces: process `SEGMENT_PATCH`, input
  `tuple val(meta), path(sdata_path), val(spec), val(index), val(n_patches)`, output
  `tuple val(meta), val(spec), path("${index}.parquet"), val(n_patches)` and `versions.yml`.
  The script writes `spec` to `spec.json` with `groovy.json.JsonOutput`. Cellpose `gpu`
  becomes `method_kwargs.gpu`; InstanSeg gets `device: 'cpu'`. Keep today's CUDA check when
  `task.accelerator` is set.

- [ ] **Step 1: Write the failing tests**:
  - `image_key_for({'cell_segmentation_image': 'img'}, 'projected') == 'img_projected'`
  - `image_key_for({}, 'full')` raises `ValueError` naming the missing attribute.
  - `method_arguments({'method': 'cellpose', 'channels': ['a'], 'method_kwargs': {'diameter': 30}})`
    has `flow_threshold == 2` and `cellprob_threshold == -6` (Review Focus 1).
  - A spec value overrides the default: `flow_threshold: 0.4` stays 0.4.
- [ ] **Step 2:** `uv run pytest tests/unit/test_segment_patch.py -v` → FAIL.
- [ ] **Step 3:** Implement. `main()` mirrors `_run_staining_segmentation` in
      `sopa/cli/segmentation.py:279-334`: `read_zarr_standardized`, `getattr(methods, name)(**kw)`,
      `StainingSegmentation(..., image_key=key, **segmentation_kwargs)`, then
      `write_patch_cells(tmpdir, index)` and move the file to `--output`. Stub: `touch ${index}.parquet`.
- [ ] **Step 4:** Test → PASS; `prek` passes (stub and versions hooks).
- [ ] **Step 5:** Commit `Add SEGMENT_PATCH with explicit image key`.

### Task 4: RESOLVE per spec, outside the store

**Files:**

- Create: `bin/resolve_segmentation.py`, `modules/local/resolve/{main.nf,meta.yml,environment.yml}`
- Test: `tests/unit/test_resolve_segmentation.py`

**Interfaces:**

- Produces: `resolve_segmentation.py --sdata S --spec spec.json --patches DIR --output NAME.parquet`.
  Pure: `assign_ids(cells: GeoDataFrame, image_key: str, target: str) -> GeoDataFrame`
  (index `{image_key}_{target}_{n}`, index name `cell_id`); `check_not_empty(cells, name)`
  raises `ValueError` with `"segmentation '<name>' found no cells"`.
- Produces: process `RESOLVE`, input `tuple val(meta), path(sdata_path), val(spec), path(parquets)`,
  output `tuple val(meta), val(spec), path("${spec.name}.parquet")`. Reads the store only for
  the image key.

- [ ] **Step 1: Write the failing tests**: `assign_ids` on 3 polygons with `('img', 'nuclei')`
      gives `['img_nuclei_0', 'img_nuclei_1', 'img_nuclei_2']`; `check_not_empty` on an empty
      frame raises with the spec name; empty parquets mixed with non-empty ones concatenate without
      error (Review Focus 2; test a helper `read_patches(paths) -> GeoDataFrame` that skips empty
      files).
- [ ] **Step 2:** `uv run pytest tests/unit/test_resolve_segmentation.py -v` → FAIL.
- [ ] **Step 3:** Implement; `main()` calls sopa's `solve_conflicts`, then `assign_ids`,
      `check_not_empty`, `to_parquet`. Stub: `touch ${spec.name}.parquet`.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `Add RESOLVE per segmentation`.

### Task 5: Hole-aware aggregation and table assembly

**Files:**

- Create: `bin/aggregate_compartments.py`
- Delete: `bin/set_cell_metadata.py`, `tests/unit/test_set_cell_metadata.py` (its `label_cells`
  moves here with its tests)
- Modify: `modules/local/aggregate/main.nf` (rewrite)
- Test: `tests/unit/test_aggregate_compartments.py`

**Interfaces:**

- Produces: `rasterize(shape, out_shape, xy_min) -> np.ndarray` and
  `mean_intensities(image: DataArray, shapes: GeoDataFrame) -> np.ndarray` (n_shapes ×
  n_channels), copied from sopa 2.2.12 `shapes/_rasterize.py` and
  `aggregation/channels.py::_aggregate_channels_aligned`, with sopa's BSD-3-Clause header and
  a `# From sopa 2.2.12 (<file>); change: holes rasterized as 0` line. `expand_radius_ratio`
  stays, applied to the cell compartment only. `min_intensity_ratio` is removed (it dropped
  cells; filtering is the later release): delete the param and add it to `removed`.
- Produces: `build_table(cells: GeoDataFrame, x: np.ndarray, var_names: list[str],
layers: dict[str, np.ndarray], obs_extra: DataFrame | None, region: str, slide: str,
core_id: str | None, specs: list[dict]) -> AnnData`, parsed with `TableModel.parse(region=region,
region_key='region', instance_key='cell_id')`; `obs_names` are the cell index unchanged.
- Produces: `aggregate_compartments.py --sdata S --method M --cells C.parquet
[--nuclei-compartment N.parquet --cytoplasm Y.parquet --links L.parquet] --specs specs.json
--slide X [--core-id Y] [--expand-radius-ratio R] --output {M}_table.h5ad`. Image is the
  `cell_segmentation_image` attribute (always the full image).
- Produces: process `AGGREGATE`, input `tuple val(meta), path(sdata_path), val(method), val(specs), path(shapes)`,
  output `tuple val(meta), val(method), path("${method}_table.h5ad")`.

- [ ] **Step 1: Write the failing tests**:
  - Ring: image 1 channel 20×20, value 100 inside a 6×6 square at the centre, 10 elsewhere;
    a 16×16 square with that 6×6 hole → mean 10. sopa's exterior-only behaviour would give
    about 21.
  - A two-part `MultiPolygon` averages both parts.
  - `build_table` keeps `obs_names == cells.index`, `obs['slide']` categorical, `obs['core_id']`
    only when given, `uns['segmentation'] == specs`, `layers` absent when none given.
  - The old `label_cells` tests, moved.
- [ ] **Step 2:** `uv run pytest tests/unit/test_aggregate_compartments.py -v` → FAIL.
- [ ] **Step 3:** Implement. Holes: rasterize each exterior as 1, then each interior as 0.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `Aggregate compartments with holes honoured`.

### Task 6: WRITE_SEGMENTATIONS, the only writer

**Files:**

- Create: `bin/write_segmentations.py`, `modules/local/write_segmentations/{main.nf,meta.yml,environment.yml}`
- Modify: `bin/project_channels.py` (`project` stops setting `cell_segmentation_image`;
  delete `drop`), `tests/unit/test_project_channels.py`
- Delete: `modules/local/drop_projection/`
- Test: `tests/unit/test_write_segmentations.py`

**Interfaces:**

- Produces: `write_segmentations.py --sdata S --shapes NAME.parquet... --tables NAME.h5ad...
[--keep-projection]`. Element name is the file stem. Each element: delete if present, then
  write (idempotent, Review Focus 3). Then deletes `{image}_projected` unless kept. Then
  re-reads the store and raises if any element or table is missing or a table's `region` is
  not among the written shapes.
- Produces: process `WRITE_SEGMENTATIONS`, input
  `tuple val(meta), path(sdata_path), path(shapes), path(tables)`, output
  `tuple val(meta), path(sdata_path)`, `versions.yml`. `ext.args` from `keep_projection`.

- [ ] **Step 1: Write the failing tests** on a store built in `tmp_path` with spatialdata:
      writes `cellpose_cells` and `cellpose_table`; running twice leaves one of each with the same
      rows; a table whose region names a missing shape raises; `img_projected` is gone without
      `--keep-projection` and present with it. `project_channels` test: the attribute is unchanged
      after `project`.
- [ ] **Step 2:** `uv run pytest tests/unit/test_write_segmentations.py tests/unit/test_project_channels.py -v` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `Add WRITE_SEGMENTATIONS as the only store writer`.

### Task 7: QC and merge read a named table

**Files:**

- Modify: `bin/qc_metrics.py:445`, `bin/qc_images.py:77-90,651-654`, `modules/local/qc_metrics/main.nf`,
  `modules/local/qc_images/main.nf`, `bin/merge_spatialdata.py`
- Test: `tests/unit/qc/test_qc_metrics_store.py`, `tests/unit/qc/test_qc_images.py`,
  `tests/unit/test_merge_spatialdata.py`

**Interfaces:**

- Produces: `--table NAME` (required) on `qc_metrics.py` and `qc_images.py`; the modules pass
  `--table ${meta.table}`. `qc_images.boundaries_name` reads the region, no longer a fixed
  `*_boundaries` list.
- `merge_spatialdata.py` already loops over tables; add a test with `cellpose_table` and
  `instanseg_table` in one core, both retargeted.

- [ ] **Step 1: Write the failing tests**: metrics on a store whose only table is
      `instanseg_table`; boundaries name `instanseg_cells` resolved from the region; merge of a
      core with two tables gives `c1__cellpose_table` and `c1__instanseg_table` with retargeted regions.
- [ ] **Step 2:** `uv run pytest tests/unit -v` → new tests FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `QC and merge take a named table`.

### Task 8: Wire the generic segmentation, one method, cells only

Output names change here. The pipeline must work end to end after this task.

**Files:**

- Create: `subworkflows/local/segmentation/main.nf`
- Delete: `subworkflows/local/{cellpose,instanseg}/`, `modules/local/{patch_segmentation_cellpose,patch_segmentation_instanseg,resolve_cellpose,resolve_instanseg}/`
- Modify: `workflows/histo.nf`, `modules/local/utils.nf` (drop `cellpose`, `instanseg`,
  `aggregate` groups and `boundariesKey`), `conf/base.config`, `conf/gpu.config`,
  `conf/sizes.config`, `conf/modules.config`, `nextflow.config` + schema (`segment_cells`
  default `true`, `segment_nuclei` default `false`; remove `instanseg_target` and add it to
  `removed` with `'use segment_cells and segment_nuclei'`), `subworkflows/local/qc/main.nf` (pass
  `meta.table`)
- Test: `tests/default.nf.test`, `tests/instanseg.nf.test`, `tests/projection.nf.test`,
  `tests/gpu.nf.test`, `tests/tma.nf.test`, `tests/instanseg_memory.nf.test`,
  `tests/args_cli.nf.test`, `tests/exemplar001.nf.test:70`, `tests/exemplar002.nf.test`

**Interfaces:**

- `SEGMENTATION(ch_patches, ch_markers, specs)` takes `[meta, sdata, patches_file]`, the
  marker sheets, and `segmentationSpecs(params)`; emits `sdata` `[meta, sdata]` after
  `WRITE_SEGMENTATIONS`, and `versions`. Inside:
  - Fill InstanSeg `channels` per sample with `defaultInstansegChannels(sheet, spec.target)`
    and set `spec.memory_gb` with `instansegMemoryGB`; keep the >64 GB warning.
  - `include { SEGMENT_PATCH as SEGMENT_PATCH_CELLPOSE; SEGMENT_PATCH as SEGMENT_PATCH_INSTANSEG }`:
    one module, two names, so config selectors, GPU and memory stay per method and the trace
    names the method. Branch on `spec.method`.
  - Group patches with `groupKey([meta.sdata_dir, spec.name], n_patches)`.
  - `AGGREGATE` per `[sample, method]`. Join its table with that method's shapes files by
    `[meta.sdata_dir, method]`, then group per sample with
    `groupKey(meta.sdata_dir, specs*.method.unique().size())` for `WRITE_SEGMENTATIONS`.
- QC input meta gains `table: "${method}_table"` and `method`.
- Selectors: `PATCH_SEGMENTATION_(CELLPOSE|INSTANSEG)` → `SEGMENT_PATCH_(CELLPOSE|INSTANSEG)`,
  `RESOLVE_*` → `RESOLVE`, add `LINK_COMPARTMENTS` and `WRITE_SEGMENTATIONS` rows in every
  size profile (as `RESOLVE`), `memory_gb` read from `spec.memory_gb`.
- `validateParams`: keep "exactly one method" for now; add "at least one of `segment_cells`,
  `segment_nuclei`" and, until Task 11, reject `segment_nuclei`.

- [ ] **Step 1: Update the failing tests** first: process names (`SEGMENT_PATCH_INSTANSEG`
      count 2, `RESOLVE` 1, `WRITE_SEGMENTATIONS` 1), `exemplar001` checks
      `shapes/cellpose_cells` and `tables/cellpose_table`, `args_cli` drops the removed groups.
- [ ] **Step 2:** `nf-test test --tag stub,validation` → FAIL.
- [ ] **Step 3:** Implement; explain any Groovy subtlety in a one-line comment.
- [ ] **Step 4:** `nf-test test --tag stub,validation` → PASS;
      `nextflow run . -profile test,laptop -stub --outdir results` → succeeds.
- [ ] **Step 5:** Optional, per memory "Mac real runs sparingly": one real run of a one-patch
      exemplar-001 crop with `use_instanseg` under `docker,emulate_amd64,laptop`, then open the
      store and check `instanseg_cells` and `instanseg_table` exist and counts match. Ask the user
      first.
- [ ] **Step 6:** Commit `Run segmentation through one generic subworkflow`.

### Task 9: Both methods together

**Files:**

- Modify: `subworkflows/local/utils_nfcore_histo_pipeline/main.nf` (`validateParams`),
  `subworkflows/local/qc/main.nf`, `workflows/histo.nf` (MERGE_REPORT grouping),
  `conf/gpu.config`
- Test: `tests/validate_params.nf.test`, new `tests/two_methods.nf.test` (tag `stub`)

**Interfaces:**

- `validateParams`: at least one of `use_cellpose`, `use_instanseg`; drop the `use_gpu` +
  `use_instanseg` rejection; `use_gpu` with InstanSeg logs
  `"use_gpu applies to Cellpose; InstanSeg runs on CPU (sopa cannot run it on CUDA yet)"`.
- QC: join markers, unsubtracted image and registration per sample first, then `flatMap` one
  row per method. Joins happen before the expansion because `join` pairs only the first item
  per key.
- `MERGE_REPORT` groups metrics by `[slide, method]`.

- [ ] **Step 1: Write the failing tests**: both methods, cells: `SEGMENT_PATCH_CELLPOSE` 2,
      `SEGMENT_PATCH_INSTANSEG` 2, `RESOLVE` 2, `AGGREGATE` 2, `WRITE_SEGMENTATIONS` 1,
      `QC_REPORT` 2; validation: neither method fails with its message; `use_gpu` + both passes.
- [ ] **Step 2:** `nf-test test tests/two_methods.nf.test tests/validate_params.nf.test` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `nf-test test --tag stub,validation` → PASS.
- [ ] **Step 5:** Commit `Allow Cellpose and InstanSeg in one run`.

### Task 10: Link nuclei to cells

**Files:**

- Create: `bin/link_compartments.py`, `modules/local/link_compartments/{main.nf,meta.yml,environment.yml}`
- Test: `tests/unit/test_link_compartments.py`

**Interfaces:**

- Produces: `link(cells: GeoDataFrame, nuclei: GeoDataFrame) -> Linked`, a dataclass with
  `nuclei` (adds `cell_id`, None when unlinked), `links` (DataFrame indexed by cell:
  `n_nuclei`, `nucleus_id`, `nucleus_area`, `cytoplasm_area`), `nucleus_compartment` and
  `cytoplasm` (GeoDataFrames indexed by cell, only cells with ≥ 1 nucleus and non-empty
  geometry). Constant `MIN_SHARE = 0.5` with a one-line why.
- Produces: `link_compartments.py --cells C --nuclei N --method M --out-dir .` writing
  `{M}_nuclei.parquet` (with `cell_id`), `{M}_cytoplasm.parquet`,
  `{M}_nucleus_compartment.parquet`, `{M}_links.parquet`.
- Produces: process `LINK_COMPARTMENTS`, input `tuple val(meta), val(method), path(cells), path(nuclei)`.

- [ ] **Step 1: Write the failing tests**, one per spec rule plus Review Focus 4 and 5:
  - nucleus 80% inside cell A → `cell_id == A`; 40% inside → unlinked
  - two nuclei in one cell → `n_nuclei == 2`, `nucleus_id` the larger, compartment is their
    union clipped to the cell
  - nucleus sticking out → compartment clipped; cytoplasm = cell − compartment (has a hole)
  - nucleus filling the cell → no cytoplasm row, `cytoplasm_area == 0`
  - cell with no nucleus → `n_nuclei == 0`, no compartment rows
  - 50/50 split between cells 0 and 1 → linked to 0
  - a difference returning a `GeometryCollection` with a line keeps only the polygon
  - empty nuclei frame → all `n_nuclei == 0`, no error
  - every cell appears once in `links`; duplicate cell index raises
- [ ] **Step 2:** `uv run pytest tests/unit/test_link_compartments.py -v` → FAIL.
- [ ] **Step 3:** Implement with `geopandas.sjoin(predicate='intersects')`, intersection
      areas, `idxmax` per nucleus with ties broken by cell order.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `Add LINK_COMPARTMENTS`.

### Task 11: Nuclei, cytoplasm and compartment layers end to end

**Files:**

- Modify: `subworkflows/local/segmentation/main.nf`, `bin/aggregate_compartments.py`,
  `bin/qc_metrics.py`, `bin/qc_report.py`, `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`
  (lift the Task 8 `segment_nuclei` rejection), `modules/local/utils.nf` (`segmentationTargets`)
- Test: `tests/unit/test_aggregate_compartments.py`, `tests/unit/qc/test_qc_metrics.py`,
  new `tests/nuclei_and_cells.nf.test` (tag `stub`)

**Interfaces:**

- Per method with both targets: RESOLVE (cells), RESOLVE (nuclei) → LINK_COMPARTMENTS →
  AGGREGATE with nucleus compartment, cytoplasm and links → WRITE_SEGMENTATIONS gets
  `{m}_cells`, `{m}_nuclei` (from LINK), `{m}_cytoplasm`, `{m}_table`. The nucleus compartment
  is not written.
- Nuclei only: AGGREGATE on the nuclei, region `{m}_nuclei`, no layers.
- Table: `layers['nucleus']`, `layers['cytoplasm']` NaN where the row is missing; `obs` gets
  `n_nuclei`, `nucleus_id`, `nucleus_area`, `cytoplasm_area` from links.
- `qc_metrics.py` adds `linking: {cells_by_n_nuclei: {0: n, 1: n, '2+': n}, unlinked_nuclei: n,
empty_cytoplasm: n}` when the table has `n_nuclei`; `qc_report.py` shows it.

- [ ] **Step 1: Write the failing tests**: `build_table` with a cell without nucleus has NaN
      in both layers; with an empty nuclei frame every layer value is NaN (Review Focus 5); metrics
      count `unlinked_nuclei` from a fixture; stub test for InstanSeg nuclei + cells (`RESOLVE` 2,
      `LINK_COMPARTMENTS` 1, `AGGREGATE` 1) and the exhaustive run (`RESOLVE` 4, `LINK` 2,
      `AGGREGATE` 2), plus the TMA profile with nuclei (merge runs).
- [ ] **Step 2:** Run them → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest tests/unit && nf-test test --tag stub,validation` → PASS.
- [ ] **Step 5:** Commit `Segment nuclei and quantify three compartments`.

### Task 12: Compare segmentations

**Files:**

- Create: `bin/compare_segmentations.py`, `modules/local/compare_segmentations/{main.nf,meta.yml,environment.yml}`
- Modify: `workflows/histo.nf`, `conf/modules.config` (publish to `qc/`)
- Test: `tests/unit/test_compare_segmentations.py`, `tests/two_methods.nf.test`

**Interfaces:**

- Produces: `match_share(a: GeoDataFrame, b: GeoDataFrame, min_iou=0.5) -> float`, the share
  of `a` with a one-to-one match in `b`. `compare_segmentations.py --sdata S --prefix P`
  writes `P_comparison.json` (counts, median areas, both match shares) and
  `P_comparison.html` with the 3 crops, reusing `qc_report.py`'s page helpers. Runs after
  `WRITE_SEGMENTATIONS`, only when both methods and `segment_cells`.

- [ ] **Step 1: Write the failing tests**: identical frames → 1.0; shifted by half a width →
      0.0; one extra cell in `b` → `match_share(b, a) == n/(n+1)`. Stub: `COMPARE_SEGMENTATIONS` 1
      with both methods, 0 with one.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest tests/unit && nf-test test --tag stub,validation` → PASS.
- [ ] **Step 5:** Commit `Add COMPARE_SEGMENTATIONS`.

### Task 13: Docs and bookkeeping

**Files:** `docs/output.md` (layout and a 1.x → 2.0 migration note: `table` →
`{m}_table`, `*_boundaries` → `{m}_cells`, StarDist removed), `docs/usage.md`,
`docs/decisions.md` (single writer, explicit image key, geometric linking, hole fix, StarDist
removal), `docs/pipeline_paths.mmd` + render, `CITATIONS.md`, `CHANGELOG.md` (`v2.0.0 - [unreleased]`
with a Breaking section), `ROADMAP.md` (1.5 replaced by 2.0; quantification 2.1, learned
features after; dearray-first 3.0; drop the StarDist note in "Before every release").

- [ ] **Step 1:** Edit the files. Keep `docs/` context files under 200 lines.
- [ ] **Step 2:** `nf-metro render docs/pipeline_paths.mmd -o docs/images/pipeline_paths.svg`;
      ask the user to look at the SVG.
- [ ] **Step 3:** `prek && nf-core pipelines lint` → PASS.
- [ ] **Step 4:** Commit `Document 2.0 segmentation`.

### Task 14: Cluster runs (user submits)

- [ ] **Step 1:** Propose the two `sbatch` commands from CONTRIBUTING: exemplar-001 with
      `use_cellpose`, `use_instanseg`, `segment_nuclei`; exemplar-002 with `use_instanseg`,
      `segment_nuclei`. Do not submit.
- [ ] **Step 2:** From the user's results, update the baselines in `tests/exemplar001.nf.test`
      and `tests/exemplar002.nf.test` (per-table counts, ±2%) and commit
      `Update exemplar baselines for 2.0`.
