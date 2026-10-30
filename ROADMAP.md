# Roadmap

The tracker for this project; GitHub Issues is not used. Reasoning is in
[docs/decisions.md](docs/decisions.md).

Priorities, in order: transparency, robustness, troubleshootability. Sizes are focused working
time, estimated before the release; treat them as rough.

## Next releases

Segmentation, then quantification, then learned features. Each release adds its own chapter
to the HTML QC report; MultiQC suits tool logs, not our figures.

### 1.3: segmentation input

1. **Three-channel projection** for CPSAM: split `use_projection`'s `cell`
   channel into membrane and cytoplasm. The cellpose docs say a third fluorescent channel needs
   retraining; item 3 should test it first.
2. **Report chapters**, one per stage.
3. **Preprocessing benchmark with ground truth**, on `cpsam_v2` (1.4 item 4). Score
   permutations of the steps before the model: combining (max, sum), smoothing
   (`projection_sigma`, `gaussian_sigma`), normalisation and CLAHE, and thresholds (sopa's,
   Cellpose's), against annotated cells: TissueNet (mIF, nuclear and whole-cell labels) and a
   few in-house crops. Extends `tools/benchmark_projection.py`; on Apple MPS one setting takes
   ~1.5 min per exemplar-001. Decides the defaults and item 1. 1–2 weeks.

### 1.4: segmentation backends

1. **`PATCH_SEGMENTATION_CELLPOSE` CPUs**: `process_single`, but used 133%.
2. **Resources by tile size.** Run exemplar-001 crops from 256 px to the whole image as single
   patches, CPU and GPU, and fit CPUs, memory, GPU memory and time to tile area. Replaces the
   size-profile stopgap for GPU tasks and item 1. Crops and configs are ready outside the repo.
3. **Automatic `patch_width_pixel`.** A first step reads the image size from its metadata and picks
   the width that gives 300–400 patches, capped for resources, logged and overridable. Reverses a
   decision (decisions.md, Parameters): a value derived from the image alone is the same on any
   hardware. Needs item 2 for the cap.
4. **`cpsam_v2`.** cellpose 4.2.1.1 defaults to it ("fewer spurious masks in low-contrast
   regions"), but sopa passes `cpsam`, the only weights in `josenimo/sopa:2.2.12`. Bake both
   in, select with `pretrained_model`, compare on exemplar-001 (or with 1.3 item 3). ~1 day.

### 1.5: multiple segmentations, compared afterwards

1. **Fan out per method × patch.** Patch tasks only read the image and each writes its own
   parquet, so they can run in parallel.
2. **One writer per store.** One `RESOLVE` per sample writes every method in turn, then
   `AGGREGATE` one table per method. Parallel writers would race on the root `zmetadata` and
   `.zattrs` (sopa's active-boundaries attribute) and on `table`; last writer wins, silently.
   Check whether `sopa resolve` clears all of `.sopa_cache`.
3. **Comparison chapter**: counts, areas and overlays per method.

### 1.6: quantification of every cell from every method, then filtering

1. **Aggregation beyond the mean.** sopa writes the mean and `obs.area` only. Own step after
   `AGGREGATE`: per-channel quantiles and SD as `layers`; perimeter, solidity, eccentricity in
   `obs`. Per compartment where a method gives nuclei and cells. Risk: memory on the WSI.
   Reuse the `python_sopa` image if it has scikit-image. 3–4 days.
2. **Cell filtering.** One `obs` boolean per rule plus `keep`; never drop cells. Not
   `passes_filtering`, which sopa deletes. Counts per rule in `{sample}_qc.json` and the report;
   check `MERGE_SPATIALDATA` carries the columns. 2–3 days.

### 1.7 onward: learned features

Nimbus first, then KRONOS and VirTues, one per release. One interface: image and shapes in,
`obs`/`obsm` out. Reuses 1.4's GPU and weights. None is in bioconda, so expect private images.
Check weight licences first.

### Separate track: dearray before Ashlar

It changes the preprocessing outputs, so it ships in 2.0.

Most valuable and most dangerous. Today Ashlar registers about 1000 tiles × 7 cycles in one job;
one failure ruins the slide. Per core it would be about 36 tiles × 7 cycles, giving per-core
parallelism, a better-conditioned registration, and failures limited to one core.

Hard parts:

- **Finding cores without stitching.** A downsampled mosaic from stage positions alone should
  be enough for Coreograph. Without this the idea is circular.
- **Mapping cores to tiles exactly.** An off-by-one silently crops a core.
- **Per-core, per-cycle sub-images with correct stage positions in the OME-XML.** Wrong
  positions give a confidently misregistered image with no error. Prototype first, trust last.
- **Keep BaSiCPy global.** 36 tiles per core is too few for a good profile; estimate per cycle
  on the whole acquisition, apply per core.

Order: (1) check Coreograph finds the same cores on the naive mosaic, else stop; (2) tile
mapping, verified against known cores; (3) one core, one cycle through Ashlar, compared with
the whole-slide result; (4) only then restructure `PREPROCESS_IMAGES`.

Downstream is untouched: core identity, `meta.slide` and `MERGE_SPATIALDATA` already exist.

### 2.0: breaking changes only

1. **Reject `technology` and `aggregate_channels`.** Ignored with a warning since 1.2; drop the
   `deprecated` map in `rejectUnknownParams`, so they become unknown parameters.

## Before every release

Two runs on the cluster, by hand. Images are 8.8 GB (mIF) to 14.7 GB (with Coreograph),
too large for GitHub runners.

Commands and what each run covers are in [CONTRIBUTING](docs/CONTRIBUTING.md#testing). Cell counts must stay
within ±2% of the baselines in `tests/exemplar001.nf.test` and `tests/exemplar002.nf.test`. Nothing checks `use_preprocessing = false` on real data (stub
only) or StarDist.

## Longer term

Not scheduled. The marker sheet already has the columns these need (`channel_role`, `exposure`,
`background`, `filter`).

1. **Ashlar registration QC: thresholds.** The fork's `--qc-output` is in the reports; what
   counts as bad still needs exemplar-001, exemplar-002 and a real slide behind it. Offering
   `--qc-output` upstream would let the module return to a bioconda image.
2. **Imaging QC.** Saturation per channel is under a day (the histograms exist). Focus and
   artefacts are open-ended and need labelled examples. Start on the stitched image; report, do not fail,
   until thresholds come from real datasets. 5–10 days.
3. **Read `.czi` metadata** for backsub exposure. `bioio_bioformats` is already in the BaSiCPy
   image, so no new container. `.czi` channel names are dyes, not markers: they can check the
   `filter` column, not name channels. Sheet values always win. Check Ashlar's `.czi` support on
   real files first. 1–2 weeks.
4. **Dearray across every nuclear channel** to detect cores lost between cycles. One Coreograph
   call per `dna` channel; each writes every core again, so disk grows with cycles. Decide first
   what a missing core means (drop it, fewer channels, or fail): QC or control flow. 1–1.5 weeks.
5. **H&E input.** Separate path: no preprocessing, StarDist's H&E model, morphology features,
   no QC at first. May need a new image for a WSI reader. 3–5 weeks.
6. **Documentation website** for curious users: one page per module with what it does and why,
   its tool and version, inputs, outputs, parameters and defaults, and an exemplar-001 figure.
   Generate what it can from `meta.yml` and the schema so it cannot drift. 1–2 weeks.
7. **Segmentation preview**, so users pick settings by eye instead of worrying about optimising
   them. A mode that stops after segmenting ~5 crops chosen to span the slide (dense, sparse,
   tissue edge, brightest cell marker) over a small grid: `cellprob_threshold`, `flow_threshold`,
   `clip_limit`, and with projection max or sum. An HTML sheet, settings by crops, shows each
   row's cell count, median area and nuclei inside cells, and a params snippet to paste; a rerun
   with `-resume` then reuses preprocessing. Works on copied crops, never the run's store. GPU
   only: 3 × 3 × 2 settings on 5 crops is ~30 min on an A40. Complements 1.3 item 3, which sets
   the defaults. Starts from `tools/benchmark_projection.py`. 1–2 weeks.

Items 3, 4 and dearray-first all need richer marker sheet metadata: design the columns once. If
dearray-first happens, item 4 becomes "dearray the naive mosaic once per `dna` channel".

## Open

### Findings

- **Leiden clusters are not reproducible on our one slide.** Best seed-to-seed ARI across
  resolutions 0.1 to 2.0 was 0.596, against a 0.9 floor; the report says so. Recheck on a
  second slide. Also test whether `n_iterations=2` (`bin/qc_images.py:370,387`) causes part of
  it. If it holds, show clusters as a staining summary or switch to gating.
- **Silhouette does not work for choosing Leiden resolution.** It falls monotonically with
  resolution, so it always picks the coarsest. Still reported; selection uses seed stability.
- **Every `-stub` run warns about a positional argument `true`.** Nextflow 26.04.6 leaves it in
  the args for both `-stub` and `-stub-run`. Harmless.

### Known limitations

- **Booleans cannot be set false on the command line.** `--use_qc=false` is a truthy string;
  `--use_qc false` becomes `true`. Both are rejected at startup. Coercion is impossible:
  `params` ignores writes to set keys (Nextflow 26.04.6). Use a params file.
- **Segmentation-time area filtering is off by decision.** `min_area_pixels2 = null` means
  sopa's CLI uses 0. Filtering belongs after aggregation (1.6 item 2). Note:
  `sopa/cli/resolve.py` takes `min_area` in µm², the segmentation CLI in px².
- **Resource profiles are estimates** apart from `size_tiny`. Rewrite from large-slide runs, read
  in Seqera Platform (`-with-tower`).
- **H&E is not supported**; only `ome_tif` mIF input.

### Tooling

- **Local Mac test profile for the partial path.** Ashlar, backsub, sopa, Cellpose and InstanSeg
  run under `docker,emulate_amd64,laptop`; BaSiCPy, Coreograph and StarDist do not (no AVX under
  Rosetta). A real-data test without those three would catch tool behaviour before the cluster.
  Use a one-patch crop of exemplar-001: stubs cover the wiring, and Cellpose-SAM takes 40 to
  55 min per 1600 px patch under Rosetta. See [CONTRIBUTING](docs/CONTRIBUTING.md#on-the-mac).
- **`bin/set_channel_names.py` element selection is untested.** Move it into a pure function
  and unit-test it.
- **nf-metro.** 2.1.0 renders the `ASHLAR -->|backsub| QC_METRICS` edge that 1.1.0 could not,
  but fails on the current map without it. Add the edge, pin 2.1.0, check the SVG by eye. Until
  then re-render with `nf-metro==1.1.0`, which is pinned nowhere.

### Resources and configuration

- **`ashlar`, `backsub`, `basicpy` and `coreograph` carry local patches.** Upstream still has no
  stub-aware `eval` for ashlar and backsub. Upstream backsub moved to a Seqera container; taking
  it means pre-staging a new image.
- **Singularity bind mounts** in `conf/slurm.config` are a commented TODO.

## Deferred deliberately

- **Channel names in the OME-TIFF header.** Would mean copying the whole image, since a task
  must not mutate its input. Names go in the Zarr instead.
- **Pixel size in the Zarr.** Would silently reinterpret `patch_width_pixel` as microns.
- **A cropped TMA fixture.** Coreograph may miss cores on a crop, giving a misleading red test.
- **`groupKey` for the cycle regroup.**
- **A `reference_dna` marker sheet column.** The sheet is already wide. Instead, the run stops
  when the Ashlar or Coreograph channel index is not `dna` (`skip_reference_dna_check` overrides).
- **A soft QC gate** (`qc_summary.tsv`). Few samples; each user reads their own QC report.
- **A run-level resource QC script.** Seqera Platform (`-with-tower`) shows retries and memory.
- **Running the exemplar nf-tests on the cluster.** Releases are checked by hand; revisit with
  more contributors.
- **Template 4.0.3 → 4.1.0.** `TEMPLATE` was merged into `dev` with `-s ours`, so
  `nf-core pipelines sync` will not bring it; port about 10 small hunks by hand. 1–2 h.
