# 3.4: learned features, starting with Nimbus

ROADMAP "3.4 onward". This adds an optional stage after segmentation. The stage runs per-cell
models on the image and the cells. Nimbus is the first model; KRONOS and VirTues plug into the
same stage later.

## Goal

With `use_nimbus`, each segmentation method gets a second table, `{method}_nimbus`. It holds one row
per cell, the same rows as `{method}_table`, with one column per marker. Each value is a Nimbus
confidence score in [0, 1].

Models are chosen as segmentation methods are: one `use_<model>` flag each, and one spec per
enabled model.

Success means all of the following hold:

- pytest passes.
- The stub nf-tests pass with Nimbus on and off.
- A parity test shows the tiled runner matches upstream Nimbus on a crop.
- On exemplar-001 the scores separate known positive and negative populations. CD45 is one check.
- Peak memory does not grow with image size.
- CPU and GPU give the same scores within float tolerance.

## Findings that shape the design

Sources are the Nimbus-Inference 0.0.5 source, sopa 2.3.0, and the KRONOS, CORAL and VirTues
repositories, read on 2026-11-11.

- **Nimbus licences.** The code and weights are MIT, and the weights are not gated (HF
  `JLrumberger/Nimbus-Inference`, `V1.pt`). A local `V*.pt` in the package's `assets/` folder, with
  `checkpoint="V1.pt"`, loads with no network call.
- **What Nimbus does.** It scores each channel on its own. The normalised channel and a binary
  whole-cell mask go in; a pixel confidence map comes out. A cell's score is the mean over its
  pixels. There is no marker vocabulary. It was trained on whole-cell masks.
- **Normalisation.** Each channel is divided by the 0.999 quantile of its nonzero pixels, then
  clipped to [0, 1]. Upstream averages the quantile over up to 10 FOVs, picked by an unseeded
  shuffle.
- **Rescaling.** Nimbus rescales by `model_magnification / magnification`, with defaults 10 and 20.
  The repository does not say how many microns per pixel "10x" means.
- **Memory.** Upstream holds each whole channel in RAM. It tiles internally at an `input_shape` of
  1024 px.
- **Test-time augmentation.** It is on by default and costs several forward passes. Nimbus
  advises turning it off on CPU.
- **sopa's wrapper is not tiled.** `sopa.aggregation.nimbus` (2.2.3+, experimental, no CLI)
  rasterises one full-image mask and writes every channel as a full-size TIFF. It suits a TMA core,
  not a whole slide.
- **Dependency clash.** Nimbus pins `numpy<2`. `josenimo/sopa:2.3.0` has numpy 2.5.4, torch 2.15
  and spatialdata 0.8.0.
- **Loading on CPU is unverified.** `torch.load` is called without `map_location`, so `V1.pt` may
  fail to load on a CPU-only node.
- **KRONOS2.** The weights are CC-BY-NC-ND and gated, and the terms forbid redistribution. So they
  cannot be baked into a shared image. KRONOS2 also needs marker names that match its 268-marker
  vocabulary.
- **VirTues.** The `sp31` weights are MIT and ungated. It needs a CUDA GPU (flash-attn) and a
  UniProt ID per channel. KRONOS2 gives one 768-d embedding per cell, and VirTues gives 512-d.

## Approaches

1. **Call `sopa.aggregation.nimbus`.** Least code, but memory grows with the image. That breaks
   the reason the pipeline tiles. Rejected.
2. **Our own tiled runner, chosen.** One task runs per sample × segmentation method × model. It
   loops over tile windows, as quantification does. It reuses Nimbus's own functions for input
   preparation, inference and the per-cell mean.
3. **One task per tile, then a gather.** More throughput, but more graph and queue overhead.
   Deferred: approach 2's tile function is the unit it would call, if exemplar runs are too slow.

## Parameters

**One pixel size for the pipeline.** `pixel_size` (number, µm per pixel, unset) replaces
`instanseg_pixel_size`. It is required with `use_instanseg` or `use_nimbus`, and is available to
later steps.

`instanseg_pixel_size` is deprecated, not removed. v3.1.0 is released, so removing it would force a
4.0.0. A run that gives it gets a warning naming `pixel_size`, and its value is used. Giving both
with different values stops the run. Removal waits for the next major release. The change ships in
its own commit, before any Nimbus work, and the release stays a minor one (3.2.0).

**A new schema group, "Learned features":**

| Parameter         | Type, default    | Meaning                                                                        |
| ----------------- | ---------------- | ------------------------------------------------------------------------------ |
| `use_nimbus`      | boolean, `false` | Score marker positivity per cell with Nimbus.                                  |
| `nimbus_channels` | string, unset    | Markers to score. Unset means every `marker`-role channel in the marker sheet. |

`use_gpu` also gives each Nimbus task a GPU.

**Validation.** `validateParams` stops the run in each case below, with its own message:

- `use_nimbus` without `pixel_size`.
- `use_nimbus` without `segment_cells`. Nimbus was trained on whole cells, so nucleus scores
  would mislead.
- `use_nimbus` without a marker sheet and without `nimbus_channels`.

A name in `nimbus_channels` that is not a channel of the image is caught per sample instead, in the
subworkflow, with `error()`.

`use_nimbus` without `use_gpu` only warns. The warning says CPU gives the same scores but takes
hours per whole slide. CPU stays allowed for Mac tests and small TMAs.

## Specs

`featureSpecs(params)` in `modules/local/utils.nf` mirrors `segmentationSpecs`. It returns one map
per enabled model:

```groovy
[name: 'nimbus', model: 'nimbus', channels: [...] or null, pixel_size: 0.65, gpu: true|false]
```

Channels left `null` are filled per sample from the marker sheet, as InstanSeg's are. A new model
is one more `if (args.use_<model>)` block.

## Graph

A new subworkflow, `LEARNED_FEATURES`, runs after `SEGMENTATION`, and only when a model is enabled.
QC, `COMPARE_SEGMENTATIONS` and `MERGE_SPATIALDATA` then read its output store instead of
`SEGMENTATION`'s. With no model enabled, the graph is unchanged.

```text
SEGMENTATION.out.sdata ──► NIMBUS (per store × segmentation method)
                       ──► WRITE_FEATURES (per store) ──► QC, COMPARE_SEGMENTATIONS, merge
```

**`NIMBUS`** runs once per store and segmentation method, on GPU with `use_gpu`. The store is only
read.

- **Inputs:** the image and `{method}_cells`.
- **`{method}_nimbus.h5ad`:** the scores, with obs copied from `{method}_table`.
- **`{method}_nimbus.json`:** provenance.

**`WRITE_FEATURES`** runs once per store, and is the only task that writes in this stage.

- It writes each `{method}_{model}` table.
- It refuses to write if the rows differ from `{method}_table`'s `obs_names`.
- It removes an existing element by path before writing it, as `WRITE_SEGMENTATIONS` does. So a
  retry and `-resume` give the same result.
- It runs strictly after `WRITE_SEGMENTATIONS`, and QC waits for it. Writes are never concurrent.

**Stale feature tables.** `WRITE_SEGMENTATIONS` adds `{method}_nimbus` to its pipeline-owned names.
A rerun that rewrites a method's shapes therefore also removes feature tables built from the old
shapes.

## Normalisation: per store

Normalisation is per store: per core on a TMA, per image otherwise. A slide-wide factor would
remove differences between patients' cores; per core, each core is scored on its own terms. The
cost is known: in a core with no positive cells, noise is stretched to [0, 1] and can score as
signal.

The method is as follows:

- **Factor.** Inside `NIMBUS`, the factor per channel is the 0.999 quantile of nonzero pixels.
- **Determinism.** The quantile is exact over a fixed-stride subsample of the store's image, so it
  is deterministic.
- **Methods agree.** Each segmentation method computes the factors again. They are identical, and
  the step is cheap next to inference.
- **Empty channels.** A channel with no nonzero pixel is not scored. Its column is NaN, it is
  logged, and it is listed in `uns`.

A slide-wide option is a ROADMAP item, not a parameter now.

## The `{method}_nimbus` table

A `TableModel` that annotates `{method}_cells`, with the same cell ids as `{method}_table`. It
survives the TMA merge, which copies every table and retargets its region.

- `X`: the scores, float32, cells × markers. NaN for an unscored channel, or for a cell that covers
  no pixel centre.
- `var_names`: the marker names, in marker-sheet order.
- `obs`: `region`, `slide`, `core_id` and `cell_id`, copied from `{method}_table`.
- `uns['nimbus']` records:
  - the package version, the weights file and its sha256;
  - the channels and the normalisation factor of each;
  - `pixel_size` and the magnification;
  - the tile size, the margin, the halo and test-time augmentation;
  - the device.

**Why a table, not a layer.** A layer must share `{method}_table`'s `var`, which is marker ×
statistic, so scores would be duplicated or padded with NaN. A table is also what viewers colour
cells by, so `cellpose_nimbus` / `CD3` is one selection in napari-spatialdata.

## The tiled runner

The runner is `bin/nimbus_cells.py`. Its pure functions are tested without the model.

**Tiles and windows, sized at the model's scale.** The image is resized by `pixel_size` before
inference, so sizes are set in model pixels and converted with `/ pixel_size`.

- **Tile.** The tile is 2048 model px. Each cell belongs to the tile holding its centroid.
- **Window.** It is the tile grown to cover its cells' bounds, plus a context margin.
- **Margin.** The margin is the model's halo plus 32, in model px. The halo is measured at start-up
  as `(input_shape - output_shape) // 2` of the valid-padding model, about 92 px from the
  architecture. The extra 32 covers the pooling phase and resize rounding.
- **Minimum window.** It is 1056 model px, so the valid path is always taken (see below). Windows
  clipped at the image border are shifted inward to reach it, where the image is large enough.
- **Labels.** Every shape that intersects the window is rasterised with integer labels, because
  neighbours shape the binary mask Nimbus sees. Only owned cells are scored, each exactly once.

**Inference per window.**

- The window is read one channel at a time and normalised with the store's factors.
- It then goes through Nimbus's `prepare_binary_mask`, `prepare_input_data`, `test_time_aug` and
  `segment_mean`, the same calls upstream's `predict_fovs` makes.
- `magnification` is `10 / pixel_size`, which assumes the model's "10x" is 1 µm/px. The plan's
  first task verifies this with the paper or the authors.

**Why tiling changes nothing Nimbus computes.** Verified in the Nimbus 0.0.5 source:

- **One global step, the per-channel factor.** It is computed once per store, before tiling, and
  every window gets the same factor. A channel with no factor is never passed on: Nimbus would
  quietly fall back to that window's own quantile, a per-tile normalisation.
- **No per-tile statistics in the model.** Its BatchNorm layers run in eval mode on fixed
  statistics. Test-time augmentation averages within one input.
- **Context.** A margin at least the halo gives every owned cell's pixels the same receptive field
  as whole-image inference.
- **One code path.** Upstream uses the reflect-padding model for inputs of 1024 px or less and
  tile-and-stitch with the valid model above that. The two give different results, and each switch
  reloads the weights from disk. The minimum window keeps every window on the valid path, as
  whole-slide inference upstream would be. The exception is an image smaller than the minimum,
  which upstream also runs on the reflect path.
- **Resize and pooling phase.** The window origin does not fall on the whole image's resize and
  pooling grid, so equality is close, not exact. A test with the real model measures it: one
  window against many small ones on the same crop. If the difference exceeds 0.01, the run stops
  and checks in.

**Same results on every device.** Test-time augmentation stays on, the Nimbus default, on CPU and
GPU alike. No other setting depends on the device.

**Device.** The device comes from `task.accelerator`, as in `SEGMENT_PATCH`. A requested CUDA device
that is absent fails the task.

`uns['nimbus']` also records the tile size, the margin and the measured halo.

## Container

The plan's first task is a spike. It builds `docker.io/josenimo/nimbus:0.0.5` FROM
`josenimo/sopa:2.3.0`:

- It installs `Nimbus-Inference==0.0.5 --no-deps` plus its real runtime dependencies.
- It bakes `V1.pt` into `nimbus_inference/assets/`.
- It sets `HF_HUB_OFFLINE=1`.

The spike passes when three things hold under numpy 2:

1. Nimbus imports.
2. `V1.pt` loads on CPU.
3. On one exemplar-001 crop that fits a single window, our runner equals upstream `predict_fovs`
   within 1e-4. Upstream runs in a plain numpy<2 environment.

If the spike fails, the fallback is a sopa-image step that exports tile arrays for `NIMBUS` to
read. That doubles disk I/O but keeps the environments apart. Choosing it needs a short check-in.

The Dockerfile goes in `tools/containers/nimbus/`. The image is listed in `containers.tsv`, and is
pre-staged as the sopa image is.

## Resources

- **Memory is flat.** `NIMBUS` holds one window × channel at a time. It uses `process_medium` and 4
  CPUs, as `SEGMENT_PATCH` does.
- **Time grows with area × channels.** Roughly hours per whole slide on CPU and minutes on an A40,
  both unmeasured. So the time limit is generous, and 3.2's sizing replaces it.
- **GPU.** `conf/gpu.config` adds `NIMBUS` to the accelerator selector.

## Extending to KRONOS and VirTues

Every model follows the same contract:

- **One flag and one spec.** Each model adds `use_<model>` and one spec block.
- **One module per model.** Its input is `[meta, sdata, method, spec]`, plus any model-specific
  extras. Its outputs are `{method}_{model}.h5ad` and `.json`, with the same rows as
  `{method}_table`.
- **One table per model and method.** Scores have markers as `var`. Embeddings have dimensions as
  `var` (`kronos_0` …).
- **Shared plumbing.** `LEARNED_FEATURES` branches on `spec.model`, as `SEGMENTATION` branches on
  `spec.method`. `WRITE_FEATURES` writes whatever tables arrive.

Adding a model touches about ten places:

- `nextflow.config` and `nextflow_schema.json`: `use_<model>` and its parameters, then
  `assets/params_template*.yml` through the prek hook.
- `validateParams` (`utils_nfcore_histo_pipeline`): its requirements, and any channel check.
- `featureSpecs` (`modules/local/utils.nf`): its spec block.
- `LEARNED_FEATURES`: the model guard, its channel resolution, its `branch` entry and its mix into
  `ch_scores`.
- Its module under `modules/local/`, with `meta.yml`, a stub and `versions.yml`.
- `conf/modules.config`, `conf/base.config`, `conf/gpu.config` and `conf/sizes.config`: publishing,
  resources, accelerator and sizing.
- `containers.tsv` and `tools/container_manifest.py`: its image.
- `LEARNED_MODELS` in `bin/write_segmentations.py`. Forgetting it leaves a stale table from old
  shapes after a re-segmentation with the model off.
- `CITATIONS.md`, `CHANGELOG.md`, `docs/output.md` and the site module page.

Each later model needs decisions of its own, kept out of this release:

- **KRONOS2:** a weights path supplied per user, not baked in, and a vocabulary check that fails
  loudly.
- **VirTues:** a `uniprot_id` marker-sheet column, and a check that refuses to run without a GPU.

## Tests

**pytest**, in `tests/unit/test_nimbus_cells.py` and `test_write_features.py`. A fake model
returns the normalised input, so means are hand-computable.

- **Ownership.** Every cell is scored exactly once, for any tile size. With the fake model, scores
  are independent of tile size.
- **Windows.** Neighbours are present in the binary mask, and cells at the window edge are whole.
- **Normalisation.** The quantile is deterministic, and an empty channel gives a NaN column.
- **Writer.** It writes the table and `uns`, refuses a row mismatch, and is idempotent on rerun.
  `WRITE_SEGMENTATIONS` removes a stale `{method}_nimbus`.
- **Specs.** `featureSpecs` and the default channels from the marker sheet.

**nf-test:**

- Stub runs: Nimbus with one method, with two methods, and on a TMA.
- With `use_nimbus` off, the graph is unchanged.
- Validation: each new `validateParams` rule, and the deprecated `instanseg_pixel_size` (warns; both differing stops).
- Every existing test that sets `instanseg_pixel_size` moves to `pixel_size`.

**Container and real data.**

- The parity test runs in the container on the Mac, on a one-patch crop, as CONTRIBUTING allows.
- The same crop runs on CPU on the Mac and on GPU on the cluster, and the scores are compared.
- Then exemplar-001 runs on the cluster. I propose the commands; you submit them.

## Docs and release

**Release.** The release is minor, 3.2.0. In `CHANGELOG.md`, Nimbus goes under Added and the
`instanseg_pixel_size` deprecation under Deprecated. The site tutorials and parameter pages move to
`pixel_size`, and the parameter reference is regenerated.

**Stale version docs fixed first.** v3.0.0 and v3.1.0 are published releases (2026-11-07). On dev,
however:

- `manifest.version` still says 2.0.0;
- the CHANGELOG lists 3.0.0 as unreleased;
- the CHANGELOG has no 3.1.0 entry.

A separate commit sets the manifest to 3.1.0, dates 3.0.0, and adds 3.1.0 from
`git log v3.0.0..v3.1.0`.

**Other docs:**

- `docs/output.md`: the `{method}_nimbus` table, a snippet to read one marker's scores, and the
  `uns` keys.
- `docs/usage.md`: `pixel_size`, a GPU recommendation, and the cost of test-time augmentation.
- `docs/decisions.md`, a "Learned features" entry covering:
  - a stage after segmentation, with one table per model;
  - tile windows;
  - per-store normalisation and why;
  - test-time augmentation fixed on;
  - cells only;
  - one pixel size.
- The `site/` module page for Nimbus.
- `CITATIONS.md` (Nimbus).
- `ROADMAP.md`: Nimbus out of 3.4; a slide-wide normalisation option added.
- `containers.tsv` and the metro map, re-rendered for a human to check.

**A minimal QC chapter**, per marker: the fraction of cells scoring above 0.5 and the median score.
It goes in `_qc.json` and the report. It is the last task, so it can be cut.

## Out of scope

- Using the scores in cell filtering (3.0 item 1).
- Slide-wide normalisation.
- Nimbus fine-tuning.
- Saving per-pixel prediction maps.
- One task per tile.
- KRONOS and VirTues themselves.
- Reading the pixel size from OME metadata.

## Settled in review (2026-11-11)

1. Normalisation is per core on TMAs, to keep inter-patient differences.
2. Whole cells only.
3. One `pixel_size` for the pipeline; `instanseg_pixel_size` is deprecated, so the release stays minor.
4. GPU is recommended, and results are the same on CPU and GPU.
5. Scores go in a new table per method rather than a layer.
6. Tiles must not change Nimbus's maths: one global factor per store, a margin from the model's halo, and one code path.
