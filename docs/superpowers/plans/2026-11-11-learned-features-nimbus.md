# Learned features (Nimbus) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An optional `LEARNED_FEATURES` stage that writes a `{method}_nimbus` table of per-cell,
per-marker Nimbus scores into each store. It is built so KRONOS and VirTues can be added as further
models.

**Architecture:**

- `featureSpecs(params)` builds one spec per enabled model, as `segmentationSpecs` does.
- `LEARNED_FEATURES` runs after `SEGMENTATION`, with one `NIMBUS` task per store × segmentation
  method.
- Each `NIMBUS` task runs a tiled runner (`bin/nimbus_cells.py`) and writes an h5ad.
- One `WRITE_FEATURES` task per store writes the tables in.
- QC, the comparison and the merge then read that store.
- `pixel_size` replaces `instanseg_pixel_size`, which stays as a deprecated alias.

**Tech Stack:** Nextflow DSL2, nf-test, Python 3.12, spatialdata 0.8, anndata, Nimbus-Inference
0.0.5, torch, pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-learned-features-nimbus-design.md`

## Global Constraints

- **No network at run time.** Weights are baked into the image, and the image sets
  `HF_HUB_OFFLINE=1`.
- **Image and pushing.** The image is `docker.io/josenimo/nimbus:0.0.5`. The user pushes it.
  Agents never `docker push` or `git push`.
- **Schema.** Optional steps are schema booleans with `default: false`. Edit
  `nextflow_schema.json` by hand. Never edit `assets/params_template*.yml`.
- **Stubs.** Every local module that creates a file has a `stub:` block. Update a stub in the same
  commit as the outputs it mirrors.
- **Container manifest.** Regenerate `containers.tsv` with `tools/container_manifest.py` after
  adding a module.
- **Errors in operators.** Use `error()`, not `assert`, inside channel operators.
- **Commits.**
  - `git add` with explicit paths only.
  - Titles under ~60 characters, and a body of a few lines or none.
  - End with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - If prek reformats a file, re-add it and commit again.
- **Comments.** Code comments are one line of "why".
- **Pinned values.**
  - Quantile: 0.999, over nonzero pixels, once per store.
  - Model scale: model px = image px × `pixel_size`. `magnification = 10 / pixel_size`, and
    `model_magnification = 10`.
  - Script constants, in model px: `TILE_MODEL_PX = 2048`, `MIN_WINDOW_MODEL_PX = 1056`, and
    `MARGIN_EXTRA_MODEL_PX = 32`. The margin is `ceil((halo + 32) / pixel_size)` image px, where
    `halo` is measured from the loaded model.
  - Test-time augmentation is always on.
  - Score columns are float32.
  - The QC positivity threshold is 0.5.
  - The tile-invariance tolerance with the real model is max abs 0.01.
- **The Mac.** Real containers run there only on a one-patch crop, under
  `-profile docker,emulate_amd64,laptop`.
- **Release.** This is a minor release, 3.2.0, because the rename is a deprecation, not a removal.

## Review Focus

1. **Cells at tile and image edges.** Every row of `{method}_table` gets exactly one score row. A
   cell is never dropped or scored twice, including in windows clipped and shifted at the image
   border. Pinned in Task 5.
2. **Per-tile normalisation sneaking in.** Every window of a channel uses the store's single
   factor. A channel without a factor is never handed to Nimbus, which would fall back to that
   window's quantile. Pinned in Tasks 5 and 6.
3. **A channel with no nonzero pixel in a store**, such as a blank marker in one TMA core. Its
   column is NaN and listed in `uns`. The run does not crash and does not stretch noise. Pinned in
   Task 5.
4. **Tables out of step with their shapes**, such as after a `-resume` with changed segmentation.
   `WRITE_FEATURES` refuses a row mismatch, and `WRITE_SEGMENTATIONS` removes a stale
   `{method}_nimbus`. Pinned in Task 7.
5. **GPU asked for, none usable.** The task fails instead of falling back to CPU. And `V1.pt`
   loads on a CPU-only node. Pinned in Tasks 1 and 7.

---

### Task 1: Nimbus image spike, halo and parity fixture

**Gate.** If the image check fails, or the magnification cannot be pinned, stop and report to the
user before Task 5. The fallback is a sopa-image export step, and choosing it needs their agreement.

**Files:**

- Create: `tools/containers/nimbus/Dockerfile`
- Create: `tools/containers/nimbus/README.md`, with the build, save-to-tar and verify commands in
  five lines
- Create: `tools/make_nimbus_fixture.py`, which cuts the crop
- Create: `tools/nimbus_reference.py`, which produces the reference with upstream Nimbus
- Modify: `.gitignore`, adding `tests/unit/fixtures/nimbus_crop/`. The fixture is about 6 MB and is
  generated, not committed.

**Interfaces:**

- Produces: the local image `docker.io/josenimo/nimbus:0.0.5`.
- Produces: the fixture `tests/unit/fixtures/nimbus_crop/`:
  - `image.npy`: (2, 1280, 1280) uint16, from exemplar-001. Use one marker with many positive
    cells and one sparse marker.
  - `labels.npy`: int32.
  - `factors.json`: upstream's normalisation dict.
  - `reference_scores.csv`: columns `label` plus one per channel, from upstream `predict_fovs`
    with `magnification = model_magnification = 10` and `test_time_aug=True`. At 1280 px this
    takes upstream's valid tile-and-stitch path, as our windows will.
- Produces: findings, recorded in the SDD ledger and in the README.
  - **Magnification.** The µm/px of Nimbus's "10x", from the paper, the README or the issues.
    Either confirm "10x = 1 µm/px" with a citation, or record the value found and correct the spec
    before Task 6.
  - **Halo.** Load the valid model, run `nimbus.model(torch.rand(1, 2, 1024, 1024))`, and record
    `(1024 - output_side) // 2`, after upstream's `crop_by`. The architecture predicts about 92.
  - **CPU load.** Whether `V1.pt` loads on CPU without `map_location`.

- [ ] **Step 1: Write the Dockerfile.**
  - `FROM docker.io/josenimo/sopa:2.3.0`.
  - Install `pip install --no-deps Nimbus-Inference==0.0.5`.
  - Install the runtime imports the base lacks, at exact versions: alpineer, kornia,
    opencv-python-headless, pyometiff, natsort and lmdb.
  - Download `V1.pt` from HF `JLrumberger/Nimbus-Inference` into the package's `assets/` folder.
  - `ENV HF_HUB_OFFLINE=1`.
- [ ] **Step 2: Build it.**
      Run: `docker buildx build --platform linux/amd64 -t docker.io/josenimo/nimbus:0.0.5 tools/containers/nimbus`
      Expected: the build succeeds.
- [ ] **Step 3: Check the import, CPU load and halo, offline.** Run inside the image with
      `--network none`:
  - Import Nimbus and print numpy's version.
  - Construct `Nimbus(dataset=None, output_dir="", save_predictions=False, device="cpu", checkpoint="V1.pt")`.
  - Call `load_checkpoint(padding="valid")`.
  - Print the halo.

  Expected: numpy 2.x, no exception, and the halo printed. If the load fails on CUDA tensors,
  record it. Task 6 then loads the state dict with `map_location`.

- [ ] **Step 4: Make the fixture and the reference.**
  - Cut the crop: `python -I tools/make_nimbus_fixture.py <exemplar-001 store or tiff> tests/unit/fixtures/nimbus_crop`.
    Labels come from a cellpose run's `{method}_cells`.
  - Run the reference in a numpy<2 environment:
    `uv run --python 3.11 --with Nimbus-Inference==0.0.5 python -I tools/nimbus_reference.py tests/unit/fixtures/nimbus_crop`.

  Expected: `factors.json`, and `reference_scores.csv` with one row per label.

- [ ] **Step 5: Commit** the Dockerfile, the README, both tools and `.gitignore`:
      `Nimbus image spike and parity tools`.

### Task 2: Correct stale version docs

**Files:**

- Modify: `nextflow.config`, setting `manifest.version` to `'3.1.0'`.
- Modify: `CHANGELOG.md`.

- [ ] **Step 1: Date 3.0.0.** Change `## v3.0.0 - [unreleased]` to `## v3.0.0 - [2026-11-07]`.
- [ ] **Step 2: Add the 3.1.0 entry.**
  - Add `## v3.1.0 - [2026-11-07]` above it, with an Added or Changed list.
  - Derive the list from `git log --oneline v3.0.0..v3.1.0`: the site navigation and module pages
    were restructured, and the metro map was redrawn.
  - Move any 3.0.0 bullet that `git log v2.0.0..v3.0.0` shows was not in 3.0.0.
  - Above it, add `## v3.2.0 - [unreleased]` with empty Added and Deprecated lists.
- [ ] **Step 3: Check the result.**
      Run: `nextflow config . | grep -A3 manifest | grep version` and `prek run --all-files`.
      Expected: `3.1.0`, and clean.
- [ ] **Step 4: Commit.** `Correct version and CHANGELOG for 3.0.0 and 3.1.0`

### Task 3: `pixel_size`, with `instanseg_pixel_size` deprecated

**Files:**

- Modify:
  - `nextflow_schema.json`. Add `pixel_size` to the generic group: number, `minimum: 0`, with the
    description "µm per pixel of the image (OME PhysicalSizeX). Required by InstanSeg and Nimbus."
    Keep `instanseg_pixel_size`, but mark it deprecated: description "Deprecated: use pixel_size",
    and `hidden: true`.
  - `nextflow.config`: `pixel_size = null`.
  - `conf/test_exemplar00{1,2}.config`.
  - `modules/local/utils.nf`.
  - `subworkflows/local/segmentation/main.nf`.
  - `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`.
  - `docs/usage.md`, and the `site/**` pages listed by
    `git grep -l instanseg_pixel_size -- site`.
- Test:
  - `tests/validate_params.nf.test`.
  - `tests/pixel_size.nf.test` (new, `nextflow_function`).
  - Every `tests/*.nf.test` that sets `instanseg_pixel_size` moves to `pixel_size`.

**Interfaces:**

- Produces: `pixelSize(Map args) -> Number or null` in `modules/local/utils.nf`.
  - It returns `toNumber('pixel_size', args.pixel_size)` when set, else
    `toNumber('instanseg_pixel_size', args.instanseg_pixel_size)`.
  - When both are set and differ, it calls
    `error("pixel_size (${a}) and the deprecated instanseg_pixel_size (${b}) differ; set only pixel_size.")`.
  - Every pipeline read of a pixel size goes through it, including `segmentationSpecs`, where
    `method_kwargs.pixel_size` keeps its key, and the InstanSeg memory helpers.
- Produces: in `validateParams`, a `log.warn` when `instanseg_pixel_size` is set, reading
  "instanseg_pixel_size is deprecated; use pixel_size." The InstanSeg assert reads
  `use_instanseg requires pixel_size`.

- [ ] **Step 1: Write the failing tests.**
  - `pixelSize`:
    - `[pixel_size: 0.65]` gives 0.65.
    - `[instanseg_pixel_size: '0.65']` gives 0.65, a number.
    - `[pixel_size: 0.5, instanseg_pixel_size: 0.65]` fails, and stdout contains `differ; set only pixel_size`.
    - `[:]` gives null.
  - `validateParams` with `[use_instanseg: true, use_preprocessing: true]` fails with
    `use_instanseg requires pixel_size`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/pixel_size.nf.test tests/validate_params.nf.test`
      Expected: the new tests fail.
- [ ] **Step 3: Implement.** Move the tests and configs to `pixel_size`.
- [ ] **Step 4: Run the suites.**
      Run: `nf-test test --tag validation && nf-test test --tag stub`
      Expected: all pass.
- [ ] **Step 5: Update the CHANGELOG.** Under 3.2.0 Deprecated, note that `instanseg_pixel_size`
      is now `pixel_size`, which is shared by InstanSeg and Nimbus.
- [ ] **Step 6: Commit.** `Add pixel_size; deprecate instanseg_pixel_size`

### Task 4: Learned-features parameters, validation and `featureSpecs`

**Files:**

- Modify:
  - `nextflow_schema.json`. Add a new `$defs` group, `learned_features`, titled "Learned
    features", with `fa_icon` `fas fa-brain`, referenced in `allOf`.
  - `nextflow.config`.
  - `modules/local/utils.nf`.
  - `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`.
- Test: `tests/feature_specs.nf.test` (new) and `tests/validate_params.nf.test`.

**Interfaces:**

- Produces: `use_nimbus`, a boolean, default `false`. Its `help_text` reads: "**Requires:**
  `pixel_size`, `segment_cells`, and `nimbus_channels` when `use_preprocessing` is false."
- Produces: `nimbus_channels`, of type `["string", "integer"]`, default `null`.
- Produces: `featureSpecs(Map args) -> List<Map>`. With `use_nimbus`, it returns
  `[name: 'nimbus', model: 'nimbus', channels: getChannels(args.nimbus_channels, true), pixel_size: pixelSize(args), gpu: args.use_gpu ? true : false]`.
  Otherwise it returns `[]`.
- Produces: `defaultNimbusChannels(List rows) -> List<String>`, the `marker_name` of each row whose
  `channel_role == 'marker'`.

- [ ] **Step 1: Write the failing tests.**
  - `featureSpecs`:
    - `[:]` gives `[]`.
    - `[use_nimbus: true, pixel_size: 0.65]` gives one spec: `name == 'nimbus'`,
      `channels == null`, `pixel_size == 0.65`.
    - `[use_nimbus: true, pixel_size: '0.65', nimbus_channels: 'CD3, CD45']` gives
      `channels == ['CD3', 'CD45']`.
  - `defaultNimbusChannels` on rows with the roles `dna`, `marker`, `autofluorescence` and
    `marker` returns the two markers, in order.
  - `validateParams` asserts these messages:
    - `use_nimbus requires pixel_size`;
    - `use_nimbus requires segment_cells`;
    - `use_nimbus without use_preprocessing needs nimbus_channels`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/feature_specs.nf.test tests/validate_params.nf.test`
      Expected: the new tests fail.
- [ ] **Step 3: Implement.** Add the schema entries, the defaults, both functions and the three
      asserts. Also add a `log.warn` when `use_nimbus` is set without `use_gpu`: "use_nimbus without
      use_gpu: same scores, but hours per whole slide on CPU."
- [ ] **Step 4: Run the tests.**
      Run: `nf-test test --tag validation && nf-test test tests/feature_specs.nf.test`
      Expected: all pass. The schema hook also passes.
- [ ] **Step 5: Commit.** `Add use_nimbus, nimbus_channels and featureSpecs`

### Task 5: Tiled runner core, with no model

**Files:**

- Create: `bin/nimbus_cells.py`, holding the pure functions here and `main` in Task 6.
- Test: `tests/unit/test_nimbus_cells.py`

**Interfaces:**

- Consumes: `aggregate_compartments.rasterize(cell, shape, xy_min) -> np.ndarray`, 0/1 with holes
  at 0.
- Produces: constants. `QUANTILE = 0.999`, `TILE_MODEL_PX = 2048`, `MIN_WINDOW_MODEL_PX = 1056` and
  `MARGIN_EXTRA_MODEL_PX = 32`.
- Produces: `image_px(model_px: int, pixel_size: float) -> int` returns
  `ceil(model_px / pixel_size)`.
- Produces: `assign_tiles(centroids: np.ndarray, tile_size: int) -> np.ndarray`, (n, 2) int tile
  indices from (n, 2) xy.
- Produces: `tile_windows(bounds, tiles, tile_size, margin, min_window, image_shape) -> dict[tuple[int, int], tuple[int, int, int, int]]`.
  It returns `(y0, y1, x0, x1)` per tile, built in four steps:
  1. Grow the tile to cover its owned cells' bounds.
  2. Grow it by `margin`.
  3. Where a side is shorter than `min_window`, extend it, shifting inward at the image border.
  4. Clip to the image.
- Produces: `label_window(geoms, labels, window) -> np.ndarray`, an int32 label image of every
  geom intersecting the window.
- Produces: `normalisation_factors(image, channel_names, quantile=QUANTILE, max_pixels=50_000_000) -> dict[str, float | None]`.
  - The image is (c, y, x), dask or numpy.
  - The quantile is over the nonzero pixels of `image[c, ::s, ::s]`, where
    `s = ceil(sqrt(h * w / max_pixels))`.
  - A channel with no nonzero pixel gives `None`.
- Produces: `cell_means(labels, prediction, wanted) -> np.ndarray`, the mean over each wanted
  label's pixels with `np.bincount`. NaN where a label has no pixel.
- Produces: `score_cells(image, geoms, cell_labels, channel_names, factors, predict, tile_size, margin, min_window) -> np.ndarray`.
  - It returns float32, (n_cells, n_channels), in `geoms` order. Sizes are in image px.
  - `predict(channel: str, normalised: np.ndarray, labels: np.ndarray) -> np.ndarray` returns a
    probability map the shape of `normalised`.
  - `normalised = clip(window / factors[channel], 0, 1)`.
  - A channel whose factor is `None` is never passed to `predict`, and its column is NaN.
  - A channel missing from `factors` raises `KeyError`. It never falls back to a per-window
    quantile.

- [ ] **Step 1: Write the failing tests.** Use shapely boxes on a synthetic image, and the fake
      `predict = lambda ch, x, lab: x`, which makes a score the mean normalised intensity.
  - `test_every_cell_scored_once_for_any_tile_size`: a 6×6 grid of boxes, many on tile edges, at
    `tile_size` 64, 100 and 4096, with `min_window=0`. The results are equal at atol 1e-6, with no
    NaN.
  - `test_border_window_shifted_inward_to_min_window`: a 1000 px image, `tile_size=300` and
    `min_window=600`. Every window side is at least 600 and lies within the image.
  - `test_window_smaller_than_min_when_image_is`: a 400 px image gives windows of 400.
  - `test_cell_on_image_border_is_whole`: a box touching x = 0 gets the hand-computed mean.
  - `test_window_contains_neighbours`: a neighbour owned by the next tile is labelled.
  - `test_every_window_gets_the_store_factor`: a recording `predict` sees normalised windows equal
    to `clip(raw / factor, 0, 1)`, with the same factor in every window.
  - `test_missing_factor_raises`: a channel absent from `factors` raises `KeyError`.
  - `test_normalisation_deterministic_and_nonzero_only`: two calls are equal, and zeros do not
    lower the quantile, checked against `np.quantile` of the nonzero values.
  - `test_empty_channel_is_nan_column`: the factor is `None`, `predict` is never called for it,
    its column is all NaN, and the others are finite.
  - `test_cell_without_pixel_centre_is_nan`: a 0.2 px sliver gets NaN.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v`
      Expected: an ImportError, or failures.
- [ ] **Step 3: Implement.** `score_cells` reads each window one channel at a time with
      `np.asarray(image[c, y0:y1, x0:x1])`, so it never holds a whole channel.
- [ ] **Step 4: Run the tests and the linter.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v && ruff check bin/nimbus_cells.py`
      Expected: all pass.
- [ ] **Step 5: Commit.** `Nimbus runner: tiles, labels, normalisation`

### Task 6: Nimbus predictor, CLI, parity and tile invariance

**Files:**

- Modify: `bin/nimbus_cells.py`
- Test:
  - `tests/unit/test_nimbus_cells.py`, for the CLI table with the fake predictor.
  - `tests/unit/test_nimbus_model.py`. It is skipped unless `nimbus_inference` imports and the
    fixture exists.

**Interfaces:**

- Consumes: Task 5's functions, and Task 1's fixture and findings.
- Produces: `load_nimbus(device: str, batch_size: int = 4)`. It builds
  `Nimbus(dataset=None, output_dir="", save_predictions=False, test_time_aug=True, model_magnification=10, device=device, checkpoint="V1.pt")`,
  then calls `load_checkpoint(padding="valid")`. Add `map_location` only if Task 1 found it needed.
- Produces: `model_halo(nimbus) -> int`, the halo measured as in Task 1.
- Produces: `nimbus_predictor(nimbus, pixel_size: float, batch_size: int = 4) -> Callable`. Its
  `predict` mirrors the per-channel body of upstream `utils.predict_fovs`:
  1. `prepare_binary_mask(labels)`.
  2. A cv2 resize of image and mask to `round(side * pixel_size)`, skipped when `pixel_size == 1`.
  3. `prepare_input_data(img, binary_mask=mask)`.
  4. `test_time_aug(input, channel, nimbus, normalization_dict={channel: 1.0}, batch_size=batch_size)`,
     called unchanged as upstream does.
  5. A resize back with `INTER_NEAREST`.
- Produces: the CLI.

  ```text
  nimbus_cells.py --sdata S --method M --channels C1,C2 --pixel-size F --device cpu|cuda
                  --output M_nimbus.h5ad --provenance M_nimbus.json
  ```

  - **Reads:** the image named by the store's `cell_segmentation_image` attribute, `{M}_cells`,
    and `{M}_table`'s obs.
  - **Normalisation:** factors from `normalisation_factors` on that image, once per store.
  - **Sizes:** in image px, `tile = image_px(TILE_MODEL_PX, F)`,
    `margin = image_px(model_halo(nimbus) + MARGIN_EXTRA_MODEL_PX, F)` and
    `min_window = image_px(MIN_WINDOW_MODEL_PX, F)`.
  - **Rows:** `{M}_table.obs_names`. Shapes are reindexed to them.
  - **Output:** a `TableModel` with `region` `{M}_cells`, `region_key` `region` and `instance_key`
    `cell_id`.
    - `obs`: `region`, `slide`, `core_id` and `cell_id`, copied from `{M}_table`.
    - `var_names`: the channels, in the order given.
    - `X`: float32.
  - **Provenance:** `uns['nimbus']` records:
    - `nimbus_version`, `weights` (`V1.pt`) and `weights_sha256`;
    - `channels`, `factors` and `unscored`;
    - `pixel_size` and `magnification`;
    - `tile_size`, `margin`, `halo` and `min_window`;
    - `test_time_aug` and `device`.

    The provenance JSON is the same dict.

  - **Errors:** an unknown channel exits 1 and names the store's channels.

- [ ] **Step 1: Write the failing tests.**
  - `test_cli_table_layout`: a tiny store, built as in `tests/unit/test_aggregate_compartments.py`,
    run through `main` with an injected fake predictor and halo. Asserts that `obs_names` equal
    the table's, `var_names` equal the channels, `X.dtype == float32`, and that the `uns['nimbus']`
    keys are present.
  - `test_unknown_channel_exits_naming_channels`.
  - `test_parity_with_upstream`, model test: `score_cells` on the fixture with
    `nimbus_predictor(load_nimbus("cpu"), 1.0)`, factors from `factors.json`, a tile of 4096 and
    the measured margin. The crop is one window, so it takes the valid path, as the reference did.
    Asserts `assert_allclose(ours, reference, atol=1e-4)`.
  - `test_tile_invariance_real_model`, model test: the same fixture at `tile_size=256`, so many
    windows, each of at least `min_window`, against `tile_size=4096`. Asserts max abs difference
    of 0.01 or less. Print the max and the mean, for the ledger.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v`
      Expected: the new tests fail.
- [ ] **Step 3: Implement** `load_nimbus`, `model_halo`, `nimbus_predictor`, `build_table` and `main`.
- [ ] **Step 4: Run the tests on the host, then the model tests in the image.**
      Run: `pytest tests/unit/test_nimbus_cells.py -v`
      Expected: pass, with the model tests skipped.
      Run: `docker run --rm --platform linux/amd64 --network none -v "$PWD":/repo -w /repo docker.io/josenimo/nimbus:0.0.5 python -m pytest tests/unit/test_nimbus_model.py -v -s`
      Expected: pass.
      **Gate.** If tile invariance fails, stop and report the numbers. Do not raise the tolerance.
- [ ] **Step 5: Commit.** `Nimbus runner: predictor, CLI, parity and tiles`

### Task 7: `NIMBUS` and `WRITE_FEATURES` modules

**Files:**

- Create:
  - `modules/local/nimbus/main.nf`, `meta.yml` and `environment.yml`. The environment pins
    python 3.12 and pip `Nimbus-Inference==0.0.5`.
  - `bin/write_features.py`.
  - `modules/local/write_features/main.nf`, `meta.yml` and `environment.yml`, copied from
    `write_segmentations`.
- Modify: `bin/write_segmentations.py`. `RESERVED` becomes
  `^(cellpose|instanseg)_(cells|nuclei|cytoplasm|table|nimbus)$`.
- Modify: `conf/base.config`, adding `withName: NIMBUS { cpus = 4 }`.
- Modify: `conf/gpu.config`. The selector becomes `'SEGMENT_PATCH_(CELLPOSE|INSTANSEG)|NIMBUS'`.
  `NIMBUS` keeps the base memory and does not take Cellpose's GPU sizing block.
- Test: `tests/unit/test_write_features.py`

**Interfaces:**

- Produces: `NIMBUS`.
  - Input: `tuple val(meta), path(sdata_path), val(method), val(spec)`.
  - Output: `tuple val(meta), val(method), val(spec), path("${method}_nimbus.h5ad"), path("${method}_nimbus.json")`,
    and `path "versions.yml"`.
  - Directives: labels `process_medium` and `process_long`; tag
    `"${meta.sample}:${method}:nimbus"`; container `docker.io/josenimo/nimbus:0.0.5`.
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
  - `test_rerun_is_idempotent`.
  - `test_write_segmentations_removes_stale_nimbus`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/test_write_features.py -v`
      Expected: the new tests fail.
- [ ] **Step 3: Implement the scripts, both modules and the config.**
- [ ] **Step 4: Run the tests and regenerate the manifest.**
      Run: `pytest tests/unit -q && tools/container_manifest.py && tools/container_manifest.py --check`
      Expected: all pass, and `containers.tsv` has a `josenimo/nimbus:0.0.5` row.
- [ ] **Step 5: Commit.** `Add NIMBUS and WRITE_FEATURES modules`

### Task 8: `LEARNED_FEATURES` subworkflow and wiring

**Files:**

- Create: `subworkflows/local/learned_features/main.nf` and `meta.yml`
- Modify:
  - `workflows/histo.nf`.
  - `conf/modules.config`, publishing `NIMBUS` `*.json` to `${params.outdir}/learned_features/`.
  - `docs/pipeline_paths.mmd`.
- Test: `tests/nimbus.nf.test` (new)

**Interfaces:**

- Consumes: `featureSpecs`, `defaultNimbusChannels`, `NIMBUS` and `WRITE_FEATURES`.
- Produces: `LEARNED_FEATURES(ch_sdata, ch_markers, specs, methods)`.
  - It takes `[meta, sdata]` per store, the marker sheets, the `featureSpecs` list and the
    segmentation methods.
  - It emits `sdata` as `[meta, sdata]`, and `versions`.
  - Keys are `meta.sdata_dir.toString()`, as in `SEGMENTATION`.
  - The marker sheet joins only when some spec has `channels == null`.
  - An empty default channel list fails with
    `error("Sample '${meta.sample}': no marker channels for nimbus. Set nimbus_channels, or mark channels 'marker' in the marker sheet.")`.
  - When there is a sheet, `nimbus_channels` names that are not in it fail with an `error()` that
    names the sample and the names.
  - Rows branch on `spec.model`, with `nimbus:` only for now.
  - Outputs group per store with `groupKey(sdata_dir, methods.size() * specs.size())`, sorted by
    file name, then join back to the store for `WRITE_FEATURES`.
- Changes `histo.nf`:
  - `def feature_specs = featureSpecs(params)`.
  - `ch_featured` is `LEARNED_FEATURES.out.sdata` when `feature_specs` is non-empty, else
    `ch_segmented`.
  - `QC`, `COMPARE_SEGMENTATIONS`, the TMA `groupTuple` and `PUBLISH_SPATIALDATA` read
    `ch_featured`.

- [ ] **Step 1: Write the failing tests** in `tests/nimbus.nf.test`, with profile `test,laptop`,
      `-stub`, and tags `stub` and `pipeline`.
  - `test("one method: one NIMBUS, one WRITE_FEATURES, QC after it")`, with `use_nimbus = true`
    and `pixel_size = 0.65`. QC's trace `start` comes after `WRITE_FEATURES`' `complete`.
  - `test("two methods: a NIMBUS per method, one write")`, adding `use_instanseg` with
    `instanseg_channels = "DAPI"`.
  - `test("TMA: one NIMBUS per core")`, with `tests/tma.nf.test`'s params.
  - `test("use_nimbus off runs neither process")`.
  - `test("nimbus_channels naming a missing channel stops the run")`.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/nimbus.nf.test`
      Expected: failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the stub suite and lint.**
      Run: `nf-test test --tag stub && nf-core pipelines lint`
      Expected: all pass, with no new lint failures.
- [ ] **Step 5: Re-render the metro map** with the command in `docs/CONTRIBUTING.md#metro-map`.
      Ask the user to look at the svg in the final report.
- [ ] **Step 6: Commit.** `Wire LEARNED_FEATURES after segmentation`

### Task 9: Documentation and release notes

**Files:**

- Modify: `docs/output.md`, `docs/usage.md`, `docs/decisions.md`, `CITATIONS.md`, `CHANGELOG.md`
  and `ROADMAP.md`.
- Create: `site/modules/nimbus.md`, and add it to the module list in `site/myst.yml`. Write for
  bench scientists: plain language, with a table of what goes in and what comes out.
- Run: the site's parameter-reference generator (see `site/build.sh`).

- [ ] **Step 1: Write `docs/output.md`.** Cover the `{method}_nimbus` table: `X`, `var`, `obs` and
      the `uns['nimbus']` keys. Add a snippet:

  ```python
  sdata["cellpose_nimbus"][:, "CD3"].X
  ```

  Also cover `learned_features/*.json`.

- [ ] **Step 2: Write `docs/usage.md`.** Cover `pixel_size`, a GPU recommendation, test-time
      augmentation fixed on, and per-core normalisation on TMAs, with its trade-off.
- [ ] **Step 3: Add a "Learned features" section to `docs/decisions.md`.** Cover these points:
  - a stage after segmentation, with one table per model;
  - tile windows at model scale, with the margin from the measured halo and the minimum window,
    and why tiling changes nothing Nimbus computes (the spec's list, the measured invariance);
  - per-store normalisation and why;
  - test-time augmentation fixed on, upstream code unchanged;
  - cells only;
  - one pixel size;
  - weights baked in.
- [ ] **Step 4: Update the release notes.**
  - `CITATIONS.md`: the Nimbus paper, with authors, title, venue and DOI, as found in Task 1.
  - `CHANGELOG.md`, 3.2.0 Added: Nimbus.
  - `ROADMAP.md`: Nimbus out of 3.4. Under Longer term, add a slide-wide Nimbus normalisation
    option and the removal of `instanseg_pixel_size` at the next major release.
- [ ] **Step 5: Build the site.**
      Run: `site/build.sh` and `prek run --all-files`
      Expected: it builds with no broken links, and the checks are clean.
- [ ] **Step 6: Commit.** `Document Nimbus scores and pixel_size`

### Task 10: QC chapter (cuttable)

**Files:**

- Modify: `bin/qc_metrics.py`, `bin/qc_report.py` and `conf/modules.config`. `QC_METRICS` ext.args
  adds `--nimbus-table ${meta.method}_nimbus` when `params.use_nimbus`.
- Test: `tests/unit/qc/test_qc_metrics.py` and `tests/unit/qc/test_qc_report.py`

**Interfaces:**

- Produces: `nimbus_metrics(X, markers, threshold=0.5) -> dict`, giving
  `{marker: {"fraction_positive": float, "median": float}}`. It is NaN-aware, and an all-NaN
  marker gives `None` values.
- Produces: `collect(..., nimbus_table: str | None = None)` adds `metrics["nimbus"]`.
- Produces: `nimbus_section(nimbus: dict) -> str`, a `table()` with each marker's percentage
  positive and median. `build` appends it when `"nimbus" in metrics`.

- [ ] **Step 1: Write the failing tests.**
  - [0.1, 0.6, 0.9] gives a fraction of 2/3 and a median of 0.6.
  - An all-NaN column gives `None`.
  - The report contains "Nimbus" and each marker when the key is present, and neither when it is
    absent.
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `pytest tests/unit/qc -q`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests.**
      Run: `pytest tests/unit -q && nf-test test --tag stub`
      Expected: all pass.
- [ ] **Step 5: Commit.** `QC: Nimbus positivity per marker`

### Task 11: Real-data checks

No code. Record the results in the SDD ledger and the final report.

- [ ] **Step 1: Mac CPU run.** A one-patch exemplar-001 crop, following CONTRIBUTING's "On the
      Mac". Expected: success, and `cellpose_nimbus` in the store. CD45 scores are higher in the top
      decile of `CD45_mean` than in the bottom decile.
- [ ] **Step 2: Propose the cluster runs, without submitting them.**
  - Exemplar-001 with `use_nimbus` and `use_gpu`.
  - The Mac crop on GPU, for a CPU vs GPU comparison at atol 1e-3.

  Include the image pre-staging commands for `josenimo/nimbus:0.0.5`. The user pushes and submits.
