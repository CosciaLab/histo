# Learned features (Nimbus) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An optional `LEARNED_FEATURES` stage that writes a `{method}_nimbus` table of per-cell, per-marker Nimbus scores into each store. The stage is built so KRONOS and VirTues can be added as further models.

**Architecture:** `featureSpecs(params)` builds one spec per enabled model, as `segmentationSpecs` does for segmentation. `LEARNED_FEATURES` runs after `SEGMENTATION`, with one `NIMBUS` task per store × segmentation method. Each task runs a tiled runner (`bin/nimbus_cells.py`) and writes an h5ad. One `WRITE_FEATURES` task per store writes the tables in. QC, the comparison and the merge then read that store. `instanseg_pixel_size` becomes a shared `pixel_size`.

**Tech Stack:** Nextflow DSL2, nf-test, Python 3.12, spatialdata 0.8, anndata, Nimbus-Inference 0.0.5, torch, pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-learned-features-nimbus-design.md`

## Global Constraints

- No network at run time. Weights are baked into the image, and the image sets `HF_HUB_OFFLINE=1`.
- The image is `docker.io/josenimo/nimbus:0.0.5`. The user pushes it; agents never `docker push`
  or `git push`.
- Optional steps are schema booleans with `default: false`. Edit `nextflow_schema.json` by hand.
  Never edit `assets/params_template*.yml`.
- Every local module that creates a file has a `stub:` block. Update a stub in the same commit as
  the outputs it mirrors.
- `containers.tsv` is regenerated with `tools/container_manifest.py` after adding a module.
- Use `error()`, not `assert`, inside channel operators.
- Commits: `git add` explicit paths only. Titles under ~60 characters, and a body of a few lines
  or none. End with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. If prek reformats
  a file, re-add it and commit again.
- Code comments are one line of "why".
- Values pinned by the spec:
  - quantile 0.999;
  - tile 2048 px and margin 128 px, as script constants;
  - `magnification = 10 / pixel_size` and `model_magnification = 10`;
  - test-time augmentation always on;
  - score columns float32;
  - QC positivity threshold 0.5.
- On the Mac, real containers run only on a one-patch crop, under `-profile docker,emulate_amd64,laptop`.

## Review Focus

1. **Cells at tile and image edges.** Every row of `{method}_table` gets exactly one score row. A
   cell is never dropped or scored twice, including in windows clipped at the image border.
   Pinned in Task 4.
2. **A channel with no nonzero pixel in a store**, such as a blank or failed marker in one TMA
   core. Its column is NaN and listed in `uns`. The run does not crash and does not stretch noise
   by 1e8. Pinned in Task 4.
3. **Tables out of step with their shapes**, such as after a `-resume` with changed segmentation.
   `WRITE_FEATURES` refuses a row mismatch, and `WRITE_SEGMENTATIONS` removes a stale
   `{method}_nimbus`. Pinned in Task 6.
4. **Bad channel names.** If `nimbus_channels` names a channel the image lacks, the run stops
   with the sample and the missing names. Pinned in Task 7.
5. **GPU asked for, none usable.** The task fails instead of falling back to CPU. And `V1.pt`
   loads on a CPU-only node. Pinned in Tasks 1 and 6.

---

### Task 1: Nimbus image spike and parity fixture

**Gate.** If any check fails, stop and report to the user before Task 4. The fallback is a
sopa-image export step, and choosing it needs their agreement.

**Files:**

- Create: `tools/containers/nimbus/Dockerfile`
- Create: `tools/containers/nimbus/README.md` (build, save-to-tar and verify commands; five lines)
- Create: `tests/unit/fixtures/nimbus_crop/` with `image.npy` (c, y, x) uint16, `labels.npy` int32
  and `reference_scores.csv`
- Create: `tools/nimbus_reference.py`, which produces the reference with upstream Nimbus

**Interfaces:**

- Produces: the local image `docker.io/josenimo/nimbus:0.0.5`.
- Produces: the fixture `tests/unit/fixtures/nimbus_crop/`:
  - 256 × 256 px from exemplar-001, with 3 `marker` channels;
  - `reference_scores.csv` has columns `label` plus one per channel, from upstream `predict_fovs`
    with `magnification == model_magnification` and `test_time_aug=True`.
- Produces: a written finding, in the SDD ledger and in the README, for each check:
  - **Magnification.** Look for the µm/px of Nimbus's "10x" in the Nimbus paper and the
    Nimbus-Inference issues and README. Either confirm "10x = 1 µm/px" with a citation, or record
    the value found and correct the spec before Task 5.
  - **CPU load.** Whether `V1.pt` loads on CPU without `map_location`.

- [ ] **Step 1: Write the Dockerfile.**
  - `FROM docker.io/josenimo/sopa:2.3.0`.
  - `pip install --no-deps Nimbus-Inference==0.0.5`, plus its runtime imports that the base lacks:
    alpineer, kornia, opencv-python-headless, pyometiff, natsort and lmdb. Pin exact versions.
  - Download `V1.pt` from HF `JLrumberger/Nimbus-Inference` into
    `$(python -c "import nimbus_inference,os;print(os.path.dirname(nimbus_inference.__file__))")/assets/`.
  - `ENV HF_HUB_OFFLINE=1`.
- [ ] **Step 2: Build it.**
      Run: `docker buildx build --platform linux/amd64 -t docker.io/josenimo/nimbus:0.0.5 tools/containers/nimbus`
      Expected: the build succeeds.
- [ ] **Step 3: Check the import and the CPU load offline.** Run `python -c` inside the image with
      `--network none`:
  - Import `nimbus_inference.nimbus.Nimbus` and `numpy`, and print both versions.
  - Construct `Nimbus(dataset=None, output_dir="", save_predictions=False, device="cpu", checkpoint="V1.pt")`.

  Expected: numpy 2.x, and no exception. If the load fails on CUDA tensors, record it. Task 5
  then loads the state dict with `map_location`.

- [ ] **Step 4: Cut the crop and produce the reference.**
  - Cut the crop from exemplar-001's stitched image (`local_test_datasets/` or `tests/exemplar_data/`).
    Take labels from a cellpose `{method}_cells` run, or from the crop's existing mask.
  - Run `tools/nimbus_reference.py` in a numpy<2 environment:
    `uv run --python 3.11 --with Nimbus-Inference==0.0.5 python -I tools/nimbus_reference.py tests/unit/fixtures/nimbus_crop`.
  - Expected: `reference_scores.csv` with one row per label.
- [ ] **Step 5: Commit.** `Nimbus image spike and parity fixture`

### Task 2: `pixel_size` replaces `instanseg_pixel_size`

Breaking. Every reference found by `git grep -l instanseg_pixel_size -- . ':!docs/superpowers'`
moves to `pixel_size`. Do not touch the CHANGELOG's past entries.

**Files:**

- Modify:
  - `nextflow_schema.json`: `pixel_size` lives in the generic group, number, `minimum: 0`. Its
    description is "µm per pixel of the image (OME PhysicalSizeX). Required by InstanSeg and Nimbus."
  - `nextflow.config`, and `conf/test_exemplar00{1,2}.config`.
  - `modules/local/utils.nf`: `toNumber('pixel_size', args.pixel_size)`. The spec key
    `method_kwargs.pixel_size` stays.
  - `subworkflows/local/segmentation/main.nf`.
  - `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`.
  - `docs/usage.md`, and `site/**` as listed by the grep.
- Test:
  - `tests/validate_params.nf.test`.
  - Every `tests/*.nf.test` the grep lists.

**Interfaces:**

- Produces: `params.pixel_size`, a number or null.
- Produces: in `rejectUnknownParams`, `removed` values become `[version, now]` pairs. The message
  becomes `"${name} was removed in ${version} (${now})"`.
  - Existing entries use `'2.0'`.
  - The new entry is `instanseg_pixel_size: ['3.0', 'use pixel_size']`.

- [ ] **Step 1: Write the failing tests** in `tests/validate_params.nf.test`.
  - `test("instanseg_pixel_size is removed, naming pixel_size")`: a pipeline-level `nextflow_function`
    on `rejectUnknownParams` with `[instanseg_pixel_size: 0.65]`. Asserts that it fails and that
    stdout contains `instanseg_pixel_size was removed in 3.0 (use pixel_size)`.
  - `test("use_instanseg without pixel_size is rejected")`: `validateParams` with
    `[use_instanseg: true, use_preprocessing: true]`. Asserts that stdout contains
    `use_instanseg requires pixel_size`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/validate_params.nf.test`
      Expected: both new tests fail.
- [ ] **Step 3: Rename everywhere.** Then update `removed` and the message in `validateParams`.
- [ ] **Step 4: Run the suite.**
      Run: `nf-test test --tag validation && nf-test test --tag stub`
      Expected: all pass.
      Run: `git grep -n instanseg_pixel_size -- . ':!docs/superpowers' ':!CHANGELOG.md'`
      Expected: only the `removed` entry.
- [ ] **Step 5: Add the CHANGELOG entry** under the unreleased version's Breaking. Note that
      `instanseg_pixel_size` is now `pixel_size`, and that a params file still using it stops at startup.
- [ ] **Step 6: Commit.** `Rename instanseg_pixel_size to pixel_size`

### Task 3: Learned-features parameters, validation and `featureSpecs`

**Files:**

- Modify:
  - `nextflow_schema.json`: a new `$defs` group, `learned_features`, titled "Learned features",
    with `fa_icon` `fas fa-brain`. Reference it in `allOf`.
  - `nextflow.config`: the defaults.
  - `modules/local/utils.nf`.
  - `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`.
- Test: `tests/feature_specs.nf.test` (new) and `tests/validate_params.nf.test`.

**Interfaces:**

- Produces: params.
  - `use_nimbus`: boolean, default `false`. Its `help_text` reads: "**Requires:** `pixel_size`,
    `segment_cells`, and `nimbus_channels` when `use_preprocessing` is false."
  - `nimbus_channels`: `["string", "integer"]`, default `null`.
- Produces: `featureSpecs(Map args) -> List<Map>` in `modules/local/utils.nf`. With `use_nimbus`,
  it returns `[name: 'nimbus', model: 'nimbus', channels: getChannels(args.nimbus_channels, true), pixel_size: toNumber('pixel_size', args.pixel_size), gpu: args.use_gpu ? true : false]`.
  Otherwise it returns `[]`.
- Produces: `defaultNimbusChannels(List rows) -> List<String>` returns the `marker_name` of each
  row whose `channel_role == 'marker'`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/feature_specs.nf.test`, as `nextflow_function` on `featureSpecs`:
    - `[:]` gives `[]`.
    - `[use_nimbus: true, pixel_size: 0.65]` gives one spec with `name == 'nimbus'`,
      `channels == null` and `pixel_size == 0.65`.
    - `[use_nimbus: true, pixel_size: '0.65', nimbus_channels: 'CD3, CD45']` gives
      `channels == ['CD3', 'CD45']` and `pixel_size == 0.65`, a number.
  - A test on `defaultNimbusChannels` with rows of the roles `dna`, `marker`, `autofluorescence`
    and `marker` returns the two markers, in order.
  - `tests/validate_params.nf.test`, one test each, asserting these messages:
    - `use_nimbus requires pixel_size`;
    - `use_nimbus requires segment_cells`;
    - `use_nimbus without use_preprocessing needs nimbus_channels`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/feature_specs.nf.test tests/validate_params.nf.test`
      Expected: the new tests fail.
- [ ] **Step 3: Implement.** Add the schema entries, the defaults, `featureSpecs`,
      `defaultNimbusChannels` and the three asserts in `validateParams`. Also add one `log.warn` when
      `use_nimbus` is set and `use_gpu` is not. It reads: "use_nimbus without use_gpu: same scores, but
      hours per whole slide on CPU."
- [ ] **Step 4: Run the tests.**
      Run: `nf-test test --tag validation && nf-test test tests/feature_specs.nf.test`
      Expected: all pass. The schema hook also passes.
- [ ] **Step 5: Commit.** `Add use_nimbus, nimbus_channels and featureSpecs`

### Task 4: Tiled runner core, with no model

**Files:**

- Create: `bin/nimbus_cells.py`, holding the pure functions here and `main` in Task 5.
- Test: `tests/unit/test_nimbus_cells.py`

**Interfaces:**

- Consumes: `aggregate_compartments.rasterize(cell, shape, xy_min) -> np.ndarray` (0/1, holes 0).
- Produces: the constants `TILE_SIZE = 2048`, `MARGIN = 128` and `QUANTILE = 0.999`.
- Produces:
  - `assign_tiles(centroids: np.ndarray, tile_size: int) -> np.ndarray`: (n, 2) int tile indices
    from (n, 2) xy.
  - `tile_windows(bounds: np.ndarray, tiles: np.ndarray, tile_size: int, margin: int, image_shape: tuple[int, int]) -> dict[tuple[int, int], tuple[int, int, int, int]]`:
    per tile, `(y0, y1, x0, x1)`. This is the tile grown to its owned cells' bounds plus the
    margin, clipped to the image.
  - `label_window(geoms: Sequence, labels: Sequence[int], window: tuple[int, int, int, int]) -> np.ndarray`:
    an int32 label image of every geom intersecting the window.
  - `normalisation_factors(image, channel_names: list[str], quantile: float = QUANTILE, max_pixels: int = 50_000_000) -> dict[str, float | None]`:
    the image is (c, y, x), dask or numpy. The quantile is taken over nonzero pixels of
    `image[c, ::s, ::s]`, where `s = ceil(sqrt(h * w / max_pixels))`. A channel with no nonzero
    pixel gives `None`.
  - `cell_means(labels: np.ndarray, prediction: np.ndarray, wanted: np.ndarray) -> np.ndarray`:
    the mean of `prediction` over each wanted label's pixels, NaN where a label has no pixel.
    Use `np.bincount`.
  - `score_cells(image, geoms, cell_labels, channel_names, factors, predict, tile_size=TILE_SIZE, margin=MARGIN) -> np.ndarray`:
    float32, (n_cells, n_channels), in `geoms` order. Arguments:
    - `predict(channel: str, normalised: np.ndarray, labels: np.ndarray) -> np.ndarray` returns a
      probability map the shape of `normalised`;
    - `normalised = clip(window / factor, 0, 1)`;
    - a channel whose factor is `None` is not predicted, and its column is NaN.

- [ ] **Step 1: Write the failing tests.** Use shapely boxes on a synthetic `image`, and a fake
      `predict = lambda ch, x, lab: x`, which makes a score the mean normalised intensity.
  - `test_every_cell_scored_once_for_any_tile_size`: a 6×6 grid of boxes, many on tile edges, at
    `tile_size` 64, 100 and 4096. The results are equal (`np.testing.assert_allclose`, atol 1e-6),
    with no NaN.
  - `test_cell_on_image_border_is_whole`: a box touching x = 0 gets the hand-computed mean.
  - `test_window_contains_neighbours`: `label_window` for one tile includes a neighbour cell owned
    by the next tile.
  - `test_normalisation_deterministic_and_nonzero_only`: two calls are equal. Zeros do not lower
    the quantile, checked against `np.quantile` of the nonzero values.
  - `test_empty_channel_is_nan_column`: an all-zero channel gives a factor of `None` and an
    all-NaN column, while the other columns are finite.
  - `test_cell_without_pixel_centre_is_nan`: a 0.2 px sliver gets NaN.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v`
      Expected: an ImportError, or failures.
- [ ] **Step 3: Implement the functions.** `score_cells` reads each window once per channel,
      with `np.asarray(image[c, y0:y1, x0:x1])`, so it never holds a whole channel.
- [ ] **Step 4: Run the tests.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v && ruff check bin/nimbus_cells.py`
      Expected: all pass.
- [ ] **Step 5: Commit.** `Nimbus runner: tiles, labels, normalisation`

### Task 5: Nimbus predictor, CLI and parity

**Files:**

- Modify: `bin/nimbus_cells.py`
- Test:
  - `tests/unit/test_nimbus_cells.py`, for the CLI table layout with the fake predictor;
  - `tests/unit/test_nimbus_parity.py`, for the model, skipped unless `nimbus_inference` imports.

**Interfaces:**

- Consumes: Task 4's functions, and the fixture and findings from Task 1.
- Produces: `nimbus_predictor(device: str, pixel_size: float, batch_size: int = 4) -> Callable`.
  It builds `Nimbus(dataset=None, output_dir="", save_predictions=False, test_time_aug=True, model_magnification=10, device=device, checkpoint="V1.pt")`
  and returns a `predict` that mirrors the per-channel body of upstream `utils.predict_fovs`:
  1. `prepare_binary_mask(labels)`;
  2. a cv2 resize of image and mask by `10 / magnification`;
  3. `prepare_input_data(img, binary_mask=mask)`;
  4. `test_time_aug(input, channel, nimbus, normalization_dict={channel: 1.0}, batch_size=batch_size)`;
  5. a resize back with `INTER_NEAREST`.

  Call `test_time_aug` unchanged, keeping its rotation closure as upstream does, so the parity
  test holds.

- Produces: the CLI.

  ```text
  nimbus_cells.py --sdata S --method M --channels C1,C2 --pixel-size F --device cpu|cuda
                  --output M_nimbus.h5ad --provenance M_nimbus.json
  ```

  It reads the image named by the store's `cell_segmentation_image` attribute, `{M}_cells`, and
  `{M}_table`'s obs. The rows are `{M}_table.obs_names`, and shapes are reindexed to them. The
  output is a `TableModel` with:
  - `region` `{M}_cells`, `region_key` `region` and `instance_key` `cell_id`;
  - obs `region`, `slide`, `core_id` and `cell_id`, copied;
  - `var_names` the channels, in the order given;
  - `X` float32;
  - `uns['nimbus']`, which records:
    - `nimbus_version` and `weights` (`V1.pt`), with `weights_sha256`;
    - `channels`, `factors` and `unscored`;
    - `pixel_size`, `magnification`, `tile_size`, `margin` and `test_time_aug`;
    - `device`.

  The provenance JSON is the same dict. An unknown channel exits 1 and names the store's channels.

- [ ] **Step 1: Write the failing tests.**
  - `test_cli_table_layout`: a tiny store, built as in `tests/unit/test_aggregate_compartments.py`,
    run through `main` with an injected fake predictor. Asserts that `obs_names` equal the table's,
    `var_names` equal the channels, `X.dtype == float32`, and that the `uns['nimbus']` keys are present.
  - `test_unknown_channel_exits_naming_channels`.
  - `test_parity_with_upstream` loads the fixture and runs `score_cells` with `nimbus_predictor("cpu", pixel_size=1.0)`.
    The factors come from `reference_scores.csv`'s normalisation. Tile 4096 gives one window.
    Asserts `np.testing.assert_allclose(ours, reference, atol=1e-4)`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v`
      Expected: the new tests fail.
- [ ] **Step 3: Implement `nimbus_predictor`, `build_table` and `main`.**
- [ ] **Step 4: Run the tests on the host, then the parity test in the image.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v`
      Expected: pass. Parity is skipped.
      Run: `docker run --rm --platform linux/amd64 --network none -v "$PWD":/repo -w /repo docker.io/josenimo/nimbus:0.0.5 python -m pytest tests/unit/test_nimbus_parity.py -v`
      Expected: pass.
- [ ] **Step 5: Commit.** `Nimbus runner: predictor, CLI and parity test`

### Task 6: `NIMBUS` and `WRITE_FEATURES` modules

**Files:**

- Create:
  - `modules/local/nimbus/main.nf`, `meta.yml` and `environment.yml`. The environment pins
    python 3.12 and pip `Nimbus-Inference==0.0.5`.
  - `bin/write_features.py`.
  - `modules/local/write_features/main.nf`, `meta.yml` and `environment.yml`, copied from
    `write_segmentations`.
- Modify: `bin/write_segmentations.py`. `RESERVED` becomes
  `^(cellpose|instanseg)_(cells|nuclei|cytoplasm|table|nimbus)$`.
- Test: `tests/unit/test_write_features.py`; also extend `tests/unit/test_write_segmentations.py`
  if present, or add the case to `test_write_features.py`.

**Interfaces:**

- Produces: `NIMBUS`.
  - Input: `tuple val(meta), path(sdata_path), val(method), val(spec)`.
  - Output: `tuple val(meta), val(method), val(spec), path("${method}_nimbus.h5ad"), path("${method}_nimbus.json")`
    and `path "versions.yml"`.
  - Directives: label `process_medium` and `process_long`; tag `"${meta.sample}:${method}:nimbus"`;
    container `docker.io/josenimo/nimbus:0.0.5`.
  - It runs the same `gpu_check` and `device` lines as `SEGMENT_PATCH`.
  - `versions.yml` records `nimbus-inference` and `torch`.
  - The stub touches both outputs.
- Produces: `write_features(sdata_path: Path, tables: list[Path]) -> None`. For each
  `{method}_{model}.h5ad`:
  1. It raises `ValueError`, naming both tables, unless `obs_names` equal those of
     `tables/{method}_table` (read with `anndata.read_zarr`).
  2. It removes `tables/{method}_{model}` by path if present, then calls
     `write_segmentations.reconsolidate`.
  3. It writes with `write_segmentations.write_element`.
- Produces: `WRITE_FEATURES`.
  - Input: `tuple val(meta), path(sdata_path), path(tables)`.
  - Output: `tuple val(meta), path(sdata_path)` and `versions.yml`.
  - Directives: label `process_low`; container `docker.io/josenimo/sopa:2.3.0`.
  - Its stub lists the staged tables, as `WRITE_SEGMENTATIONS`' does.

- [ ] **Step 1: Write the failing tests.**
  - `test_writes_table_and_uns`.
  - `test_refuses_row_mismatch`: a reordered or shortened h5ad raises an error, and the store is
    unchanged.
  - `test_rerun_is_idempotent`: writing twice leaves one element with equal `X`.
  - `test_write_segmentations_removes_stale_nimbus`: a store holding `cellpose_nimbus`, rewritten
    by `write_segmentations` without it, loses it.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/test_write_features.py -v`
      Expected: the new tests fail.
- [ ] **Step 3: Implement the scripts and both modules.** In `conf/base.config`, set `withName: NIMBUS { cpus = 4 }`.
      In `conf/gpu.config`, extend the selector to `'SEGMENT_PATCH_(CELLPOSE|INSTANSEG)|NIMBUS'`.
      `NIMBUS` keeps the base memory and does not take Cellpose's GPU sizing block.
- [ ] **Step 4: Run the tests and regenerate the manifest.**
      Run: `pytest tests/unit -q && tools/container_manifest.py && tools/container_manifest.py --check`
      Expected: all pass, and `containers.tsv` has a `josenimo/nimbus:0.0.5` row.
- [ ] **Step 5: Commit.** `Add NIMBUS and WRITE_FEATURES modules`

### Task 7: `LEARNED_FEATURES` subworkflow and wiring

**Files:**

- Create: `subworkflows/local/learned_features/main.nf` and `meta.yml`
- Modify:
  - `workflows/histo.nf`;
  - `conf/modules.config`: publish `NIMBUS`'s `*.json` to `${params.outdir}/learned_features/`;
  - `docs/pipeline_paths.mmd`.
- Test: `tests/nimbus.nf.test` (new)

**Interfaces:**

- Consumes: `featureSpecs`, `defaultNimbusChannels`, `NIMBUS` and `WRITE_FEATURES`.
- Produces: `LEARNED_FEATURES(ch_sdata, ch_markers, specs, methods)`.
  - Takes `[meta, sdata]` per store, the marker sheets, the `featureSpecs` list and the
    segmentation methods.
  - Emits `sdata` as `[meta, sdata]` and `versions`.
  - Keys are `meta.sdata_dir.toString()`, as in `SEGMENTATION`.
  - The marker sheet joins only when some spec has `channels == null`.
  - A spec's empty default channel list fails with
    `error("Sample '${meta.sample}': no marker channels for nimbus. Set nimbus_channels, or mark channels 'marker' in the marker sheet.")`.
  - Rows branch on `spec.model` (`nimbus:` only, for now).
  - Outputs group per store with `groupKey(sdata_dir, methods.size() * specs.size())`, sorted by
    file name, then join back to the store for `WRITE_FEATURES`.
- In `histo.nf`:
  - `def feature_specs = featureSpecs(params)`.
  - `ch_featured` is `LEARNED_FEATURES.out.sdata` when `feature_specs` is non-empty, else
    `ch_segmented`.
  - `QC`, `COMPARE_SEGMENTATIONS`, the TMA `groupTuple` and `PUBLISH_SPATIALDATA` read
    `ch_featured`.

- [ ] **Step 1: Write the failing tests** in `tests/nimbus.nf.test`: profile `test,laptop`,
      `-stub`, tags `stub` and `pipeline`.
  - `test("one method: one NIMBUS per store, one WRITE_FEATURES")` with `use_nimbus = true` and
    `pixel_size = 0.65`. Asserts that `NIMBUS` ran once, `WRITE_FEATURES` once, and that QC ran
    after `WRITE_FEATURES`. Check that by comparing their trace `complete` and `start` times.
  - `test("two methods: a NIMBUS per method, one write")`, adding `use_instanseg` with
    `instanseg_channels = "DAPI"`.
  - `test("TMA: one NIMBUS per core")`, with the params `tests/tma.nf.test` uses.
  - `test("use_nimbus off runs neither process")`.
  - `test("nimbus_channels naming a missing channel stops the run")`: the error names the sample
    and the channel. The runner's exit covers real runs. Here, check the names against the marker
    sheet in the subworkflow with `error()`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/nimbus.nf.test`
      Expected: failures.
- [ ] **Step 3: Implement the subworkflow and the wiring.**
- [ ] **Step 4: Run the stub suite and lint.**
      Run: `nf-test test --tag stub && nf-core pipelines lint`
      Expected: all pass, with no new lint failures.
- [ ] **Step 5: Re-render the metro map.** Run the render command from
      `docs/CONTRIBUTING.md#metro-map`, then commit the `.mmd` and the svg. Ask the user to look at
      the svg in the final report.
- [ ] **Step 6: Commit.** `Wire LEARNED_FEATURES after segmentation`

### Task 8: Documentation and release notes

**Files:**

- Modify:
  - `docs/output.md`;
  - `docs/usage.md`;
  - `docs/decisions.md`;
  - `CITATIONS.md`;
  - `CHANGELOG.md`;
  - `ROADMAP.md`.
- Create: `site/modules/nimbus.md`, and add it to the module list in `site/myst.yml`. Write for
  bench scientists: plain language, with a table of what goes in and what comes out.
- Run: the site's parameter-reference generator (see `site/build.sh`).

- [ ] **Step 1: Write `docs/output.md`.** Cover the `{method}_nimbus` table: `X`, `var`, `obs`
      and the `uns['nimbus']` keys. Add a three-line snippet:

  ```python
  sdata["cellpose_nimbus"][:, "CD3"].X
  ```

  Also cover `learned_features/*.json`.

- [ ] **Step 2: Write `docs/usage.md`.** Cover `pixel_size`, a GPU recommendation, test-time
      augmentation fixed on, and per-core normalisation on TMAs, with its trade-off.
- [ ] **Step 3: Add a "Learned features" section to `docs/decisions.md`.** Cover these points:
  - a stage after segmentation, with one table per model;
  - tile windows;
  - per-store normalisation and why;
  - test-time augmentation fixed on, upstream's code unchanged;
  - cells only;
  - one pixel size;
  - weights baked in.
- [ ] **Step 4: Update the release notes.**
  - `CITATIONS.md`: the Nimbus paper, with authors, title, venue and DOI as found in Task 1.
  - `CHANGELOG.md` Added: Nimbus.
  - `ROADMAP.md`: Nimbus out of 3.4. Add "slide-wide Nimbus normalisation (option)" under Longer
    term.
- [ ] **Step 5: Build the site.**
      Run: `site/build.sh`
      Expected: it builds with no broken links.
      Run: `prek run --all-files`
      Expected: clean.
- [ ] **Step 6: Commit.** `Document Nimbus scores and pixel_size`

### Task 9: QC chapter (cuttable)

**Files:**

- Modify: `bin/qc_metrics.py`, `bin/qc_report.py` and `conf/modules.config`. `QC_METRICS`' ext.args
  adds `--nimbus-table ${meta.method}_nimbus` when `params.use_nimbus`.
- Test: `tests/unit/qc/test_qc_metrics.py` and `tests/unit/qc/test_qc_report.py`

**Interfaces:**

- Produces: `nimbus_metrics(X: np.ndarray, markers: list[str], threshold: float = 0.5) -> dict`.
  The result is `{marker: {"fraction_positive": float, "median": float}}`, NaN-aware. An all-NaN
  marker gives `None` values.
- Produces: `collect(..., nimbus_table: str | None = None)` adds `metrics["nimbus"]`.
- Produces: `nimbus_section(nimbus: dict) -> str`, a `table()` of the marker, the percentage
  positive and the median. `build` appends it when `"nimbus" in metrics`.

- [ ] **Step 1: Write the failing tests.**
  - `nimbus_metrics` on a hand-made matrix: [0.1, 0.6, 0.9] gives a fraction of 2/3 and a median
    of 0.6.
  - An all-NaN column gives `None`.
  - The report HTML contains "Nimbus" and each marker when the key is present, and neither when
    it is absent.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/qc -q`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests.**
      Run: `pytest tests/unit -q && nf-test test --tag stub`
      Expected: all pass.
- [ ] **Step 5: Commit.** `QC: Nimbus positivity per marker`

### Task 10: Real-data checks

No code. Record the results in the SDD ledger and in the final report.

- [ ] **Step 1: Mac CPU run.** Run on a one-patch exemplar-001 crop, following the
      CONTRIBUTING "On the Mac" pattern:
      `nextflow run . -profile docker,emulate_amd64,laptop,test_exemplar001 --use_preprocessing false --use_nimbus true …`.
      Expected: success, and `cellpose_nimbus` in the store. CD45 scores are higher in cells whose
      `CD45_mean` is in the top decile than in the bottom decile.
- [ ] **Step 2: Propose the cluster runs.** Write, but do not submit:
  - an exemplar-001 run with `use_nimbus` and `use_gpu`;
  - the same crop on GPU, for a CPU vs GPU comparison at atol 1e-3.

  Include the image pre-staging commands for `josenimo/nimbus:0.0.5`. The user pushes and
  submits.
