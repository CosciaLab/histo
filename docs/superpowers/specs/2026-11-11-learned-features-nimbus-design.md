# 3.4: learned features, starting with Nimbus

ROADMAP "3.4 onward". Adds an optional stage after segmentation that runs per-cell models on the
image and the cells. Nimbus is the first model. KRONOS and VirTues plug into the same stage later.
Additive, so a minor release.

## Goal

With `use_nimbus`, each `{method}_table` gains `obsm['nimbus']`. It is a cells × markers frame of
Nimbus confidence scores in [0, 1]. Choosing models works like choosing segmentation methods: one
`use_<model>` flag each, and one spec per enabled model.

Success means all of the following hold:

- pytest passes.
- The stub nf-tests pass with Nimbus on and off.
- A parity test shows the tiled runner matches upstream Nimbus on a crop.
- On exemplar-001 the scores separate known positive and negative populations. CD45 is one check.
- Peak memory does not grow with image size.

## Findings that shape the design

Sources are the Nimbus-Inference 0.0.5 source, sopa 2.3.0, and the KRONOS, CORAL and VirTues
repositories, read on 2026-11-11.

- **Nimbus licences.** The code and weights are MIT. The weights are not gated (HF
  `JLrumberger/Nimbus-Inference`, `V1.pt`). A local `V*.pt` in the package's `assets/` folder, with
  `checkpoint="V1.pt"`, loads with no network call.
- **What Nimbus does.** It scores each channel on its own: the normalised channel plus a binary
  whole-cell mask go in, and a pixel confidence map comes out. The cell's score is the mean over
  its pixels. There is no marker vocabulary. It was trained on whole-cell masks.
- **Normalisation.** Each channel is divided by the 0.999 quantile of its nonzero pixels, then
  clipped to [0, 1]. The quantile is averaged over up to 10 FOVs, picked by an unseeded shuffle.
- **Rescaling.** Nimbus rescales by `model_magnification / magnification`, with defaults 10 and 20.
  The microns per pixel behind "10x" are not documented.
- **Memory.** Upstream holds each whole channel in RAM. It tiles internally at `input_shape`
  1024 px.
- **Test-time augmentation.** It is on by default and costs several forward passes. Nimbus
  advises turning it off on CPU.
- **sopa's wrapper is not tiled.** `sopa.aggregation.nimbus` (2.2.3+, experimental, no CLI)
  rasterises one full-image mask and writes every channel as a full-size TIFF. It suits a TMA core,
  not a whole slide.
- **Dependency clash.** Nimbus pins `numpy<2`. `josenimo/sopa:2.3.0` has numpy 2.5.4, torch
  2.15 and spatialdata 0.8.0.
- **`torch.load` has no `map_location`.** Whether `V1.pt` loads on a CPU-only node is unverified.
- **KRONOS2.** Its weights are CC-BY-NC-ND, gated, and the terms forbid redistribution, so it
  cannot be baked into a shared image. It needs marker names that match its 268-marker vocabulary.
- **VirTues.** The `sp31` weights are MIT and ungated. It needs a CUDA GPU (flash-attn) and a
  UniProt ID per channel. Both models give one embedding per cell, 768-d and 512-d.

## Approaches

1. **Call `sopa.aggregation.nimbus`.** It has the least code. But memory grows with the image,
   which breaks the reason the pipeline tiles. Rejected.
2. **Our own tiled runner, one task per sample × segmentation method × model** (chosen). It loops
   over tile windows and reuses Nimbus's own functions for input preparation, inference and the
   per-cell mean. A separate step computes the normalisation once per slide. This follows
   quantification's tile windows.
3. **One task per tile, then a gather.** It gives more throughput but adds graph and queue
   overhead. Deferred: approach 2's tile function is the unit it would call, if exemplar runs are
   too slow.

## Parameters

There is one new schema group, "Learned features". Shared settings stay where they are, and
`use_gpu` now also covers the model tasks.

| Parameter           | Type, default    | Meaning                                                                        |
| ------------------- | ---------------- | ------------------------------------------------------------------------------ |
| `use_nimbus`        | boolean, `false` | Score marker positivity per cell with Nimbus.                                  |
| `nimbus_channels`   | string, unset    | Markers to score. Unset means every `marker`-role channel in the marker sheet. |
| `nimbus_pixel_size` | number, unset    | µm per pixel of the image. Required with `use_nimbus`.                         |

`validateParams` stops the run in these cases, each with its own message:

- `use_nimbus` without `nimbus_pixel_size`.
- `use_nimbus` without `segment_cells`. Nimbus was trained on whole cells, so nucleus scores
  would mislead.
- `use_nimbus` without a marker sheet and without `nimbus_channels`.
- A name in `nimbus_channels` that is not a channel of the image. This is checked per sample in
  the subworkflow with `error()`.

## Specs

`featureSpecs(params)` in `modules/local/utils.nf` mirrors `segmentationSpecs`. It returns one
map per enabled model:

```groovy
[name: 'nimbus', model: 'nimbus', channels: [...] or null, pixel_size: 0.65,
 output: 'obsm', gpu: true|false]
```

Channels left `null` are filled per sample from the marker sheet, as InstanSeg's are. A new model
is one more `if (args.use_<model>)` block.

## Graph

A new subworkflow, `LEARNED_FEATURES`, runs after `SEGMENTATION` and only when a model is
enabled. QC, `COMPARE_SEGMENTATIONS` and `MERGE_SPATIALDATA` then read its output store instead of
`SEGMENTATION`'s. With no model enabled, the graph is unchanged.

```text
SEGMENTATION.out.sdata ──► NIMBUS_NORMALISE (per store) ──► group by slide ──┐
                      └──► per store × segmentation method ─────────────────┴► NIMBUS
NIMBUS outputs (all methods × models of a store) ──► WRITE_FEATURES (per store) ──► QC, merge
```

- **`NIMBUS_NORMALISE`** runs once per store on CPU. It writes the 0.999 quantile of nonzero
  pixels per scored channel as JSON. The quantile is exact over a fixed-stride subsample, so it is
  deterministic.
- **Normalisation across a slide.** For a TMA, every core's NIMBUS task receives all of its
  slide's JSONs and uses the mean per channel. This is Nimbus's own rule, with cores as FOVs: all
  of them, not a random 10. A whole-slide image is its own slide.
- **Empty channels.** A channel with no foreground in any core is not scored. Its column is NaN,
  it is logged, and it is listed in `uns`.
- **`NIMBUS`** runs once per store × segmentation method, on GPU with `use_gpu`. It reads the
  image and `{method}_cells` and writes `{method}_nimbus.parquet`, indexed by cell id with one
  float32 column per marker. It also writes `{method}_nimbus.json` for provenance. The store is
  only read.
- **`WRITE_FEATURES`** runs once per store and is the only task that writes. It sets
  `obsm[name]` and `uns['learned_features'][name]` on each `{method}_table`. It refuses to write if
  the parquet index differs from the table's `obs_names`. A rerun replaces the keys, so a retry
  and `-resume` give the same result. It runs strictly after `WRITE_SEGMENTATIONS`, and QC waits
  for it, so writes are never concurrent.

## The tiled runner

The runner is `bin/nimbus_cells.py`. Its pure functions are tested without the model.

- **Tiles and windows.** Each cell belongs to the tile holding its centroid. The tile is 2048 px,
  a script constant. Its window is grown to cover its cells' bounds plus a 128 px context margin.
  Every shape that intersects the window is rasterised with integer labels, because neighbours
  shape the binary mask Nimbus sees. Only owned cells are scored, each exactly once.
- **Inference per window.** Each window is read once, as one channel at a time. It is normalised
  with the slide factors and run through Nimbus's `prepare_binary_mask`, `prepare_input_data`,
  `test_time_aug` and `segment_mean`. These are the same calls upstream's `predict_fovs` makes.
- **Settings.** Test-time augmentation stays on, the Nimbus default, on CPU and GPU alike. Turning
  it off would make results depend on hardware.
- **Rescaling.** `magnification` is set to `10 / nimbus_pixel_size`. This assumes the model's 10x
  is 1 µm/px. The plan's first task must verify it with the paper or the authors.
- **Device.** The device comes from `task.accelerator`, as in `SEGMENT_PATCH`. A requested CUDA
  device that is absent fails the task.
- **Missing scores.** A cell that covers no pixel centre gets NaN.

`uns['learned_features']['nimbus']` records:

- the package version, the weights file and its sha256;
- the channels and the normalisation factor of each;
- the pixel size and the magnification;
- the tile size, the margin and test-time augmentation;
- the device.

## Container

The plan's first task is a spike: build `docker.io/josenimo/nimbus:0.0.5` FROM
`josenimo/sopa:2.3.0`. It installs `Nimbus-Inference==0.0.5 --no-deps` plus its real runtime
dependencies, and bakes `V1.pt` into `nimbus_inference/assets/` with `HF_HUB_OFFLINE=1`.

The spike passes when three things hold under numpy 2:

1. Nimbus imports.
2. `V1.pt` loads on CPU.
3. On one exemplar-001 crop that fits a single window, our runner equals upstream `predict_fovs`.
   The upstream side runs in a plain numpy<2 environment, and the two must agree within 1e-4.

If the spike fails, `NIMBUS` reads tile arrays that a sopa-image step exports. That doubles disk
I/O but keeps environments apart. Choosing this fallback needs a short check-in.

The Dockerfile goes in `tools/containers/nimbus/`. The image is listed in `containers.tsv`, and
the image and tar are pre-staged as the sopa image is.

## Resources

- `NIMBUS` reads up to one window × channel at a time, so memory is flat. It uses
  `process_medium` and 4 CPUs, as `SEGMENT_PATCH` does.
- Time grows with area × channels. Rough figures are hours per whole slide on CPU and minutes on
  an A40. Both are unmeasured, so the time limit is generous, and 3.2's sizing replaces it.
- `conf/gpu.config` adds `NIMBUS` to the accelerator selector.

## Extending to KRONOS and VirTues

The shared contract for every model is:

- **One flag and one spec.** Each model adds `use_<model>` and one spec block.
- **One module per model.** Its input is `[meta, sdata, method, spec]` plus any model-specific
  extras. Its output is `{method}_{model}.parquet`, indexed by cell id, plus `{method}_{model}.json`.
- **Shared steps.** `LEARNED_FEATURES` branches on `spec.model`, as `SEGMENTATION` branches on
  `spec.method`. `WRITE_FEATURES` writes whatever arrives. Embeddings go in `obsm` as arrays,
  marker-wise scores as frames.

Each later model needs its own decisions, kept out of this release:

- **KRONOS2:** a weights path supplied per user, not baked in, and a vocabulary check that fails
  loudly.
- **VirTues:** a `uniprot_id` marker-sheet column and GPU-only validation.

## Tests

**pytest**, in `tests/unit/test_nimbus_cells.py` and `test_write_features.py`. A fake model
returns the normalised input, so means are hand-computable.

- Ownership: every cell is scored once, for any tile size. Scores are independent of tile size
  with the fake model.
- Neighbours are present in the binary mask, and cells at the window edge are whole.
- Normalisation: the quantile is deterministic, a slide's factors are the mean over cores, and an
  empty channel gives a NaN column.
- Writer: it writes `obsm` and `uns`, refuses an index mismatch, and is idempotent on rerun.
- `featureSpecs` and the channel defaults from the marker sheet.

**nf-test:**

- stub runs: Nimbus with one method, with two methods, and on a TMA, where all cores get one
  slide's JSONs;
- `use_nimbus` off leaves the graph unchanged;
- validation for each `validateParams` rule.

**Container and real data.** The parity test runs in the container on the Mac with a one-patch
crop, as CONTRIBUTING allows. Then exemplar-001 runs on the cluster: you submit it, and I propose
the command.

## Docs and release

- `docs/output.md`: `obsm['nimbus']`, a snippet that reads it, and the `uns` keys.
- `docs/usage.md`: pixel size, a GPU recommendation, and the cost of test-time augmentation.
- `docs/decisions.md`, a Learned features entry covering:
  - a stage after segmentation;
  - tile windows;
  - slide-level normalisation;
  - test-time augmentation fixed on;
  - cells only.
- The `site/` module page and the regenerated parameter reference.
- `CITATIONS.md` (Nimbus), `CHANGELOG.md`, and `ROADMAP.md`, which moves Nimbus out of 3.4.
- `containers.tsv` and the metro map, re-rendered for a human to check.
- A minimal QC chapter, per marker: the fraction of cells scoring above 0.5 and the median score,
  in `_qc.json` and the report. It is the last task, so it can be cut.

## Out of scope

- Using the scores in cell filtering (3.0 item 1).
- Nimbus fine-tuning.
- Saving per-pixel prediction maps.
- One task per tile.
- KRONOS and VirTues themselves.
- Units in µm.

## Assumptions to confirm before planning

1. **Slide-level normalisation for TMAs** uses the mean of per-core quantiles. The alternative is
   per core, which is simpler but inflates noise in cores negative for a marker.
2. **Nimbus requires `segment_cells`** and refuses nuclei-only runs.
3. **`nimbus_pixel_size` is a separate parameter.** The alternative is one shared pixel-size
   parameter that would also replace `instanseg_pixel_size`, which is a breaking change.
4. **Test-time augmentation is always on**, even on CPU.
5. **Scores go in `obsm['nimbus']`**, not in `X` as a `{marker}_nimbus` statistic.
