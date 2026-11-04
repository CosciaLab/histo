# Roadmap

The tracker for this project; GitHub Issues is not used. Reasoning is in
[docs/decisions.md](docs/decisions.md). Priorities, in order: transparency, robustness,
troubleshootability. Sizes are focused working time, estimated before the release; rough.

## Next releases

Resources, quantification, segmentation defaults, then learned features; each adds a QC report
chapter (MultiQC suits tool logs, not our figures). 2.0 is in the [CHANGELOG](CHANGELOG.md).

### 2.1: tiling and resources

1. **`SEGMENT_PATCH_CELLPOSE` CPUs**: `process_single`, but used 133%.
2. **Resources by tile size.** Run exemplar-001 crops from 256 px to the whole image as single
   patches, CPU and GPU, and fit CPUs, memory, GPU memory and time to tile area. Replaces the
   size-profile stopgap for GPU tasks and item 1. Crops and configs are ready outside the repo.
3. **Automatic `patch_width_pixel`.** A first step reads the image size from its metadata and picks
   the width that gives 300–400 patches, capped for resources, logged and overridable. Reverses a
   decision (decisions.md, Parameters): a value derived from the image alone is the same on any
   hardware. Needs item 2 for the cap.

### 2.2: quantification of every cell from every method, then filtering

1. **Aggregation beyond the mean.** `AGGREGATE` writes the mean per compartment and `obs.area`
   only. Extend `bin/aggregate_compartments.py`: per-channel quantiles and SD as `layers`;
   perimeter, solidity, eccentricity in `obs`. Risk: memory on the WSI. 3–4 days.
2. **Cell filtering.** One `obs` boolean per rule plus `keep`; never drop cells. Not
   `passes_filtering`, which sopa deletes. Counts per rule in `{sample}_{method}_qc.json` and the report;
   check `MERGE_SPATIALDATA` carries the columns. 2–3 days.
3. **Report chapters**, one per stage.

### 2.3: segmentation defaults

1. **`cpsam_v2`.** cellpose 4.2.1.1 defaults to it ("fewer spurious masks in low-contrast
   regions"), but sopa passes `cpsam`, the only weights in `josenimo/sopa:2.2.12`. Bake both
   in, select with `pretrained_model`, compare on exemplar-001 (or with item 2). ~1 day.
2. **Preprocessing benchmark with ground truth**, on `cpsam_v2` (item 1). Score
   permutations of the steps before the model: combining (max, sum), smoothing
   (`projection_sigma`, `gaussian_sigma`), normalisation and CLAHE, and thresholds (sopa's,
   Cellpose's), against annotated cells: TissueNet (mIF, nuclear and whole-cell labels) and a
   few in-house crops. Extends `tools/benchmark_projection.py`; on Apple MPS one setting takes
   ~1.5 min per exemplar-001. Decides the defaults and item 3. 1–2 weeks.
3. **Three-channel projection** for CPSAM: split `use_projection`'s `cell` channel into membrane
   and cytoplasm. The cellpose docs say a third channel needs retraining; item 2 tests it first.

### 2.4 onward: learned features

Nimbus first, then KRONOS and VirTues, one per release. One interface: image and shapes in,
`obs`/`obsm` out. Reuses 2.1's GPU sizing and 2.3's baked weights. None is in bioconda, so
expect private images. Check weight licences first.

### Separate track: dearray before Ashlar

Ships in 3.0: it changes the preprocessing outputs. Likely to change, as is Longer term item 4.

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

## Before every release

Two runs on the cluster, by hand. Images are 8.8 GB (mIF) to 14.7 GB (with Coreograph), too
large for GitHub runners. Commands and what each run covers are in
[CONTRIBUTING](docs/CONTRIBUTING.md#testing). Cell counts must stay within ±2% of the baselines
in `tests/exemplar001.nf.test` and `tests/exemplar002.nf.test`. Nothing checks
`use_preprocessing = false` on real data (stub only).

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
5. **H&E input.** Separate path: no preprocessing, an H&E nuclear model, morphology features,
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
   only: 3 × 3 × 2 settings on 5 crops is ~30 min on an A40. Complements 2.3 item 2, which sets
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
- **`use_gpu` applies to Cellpose only; InstanSeg runs on CPU.** sopa calls `.numpy()` on its
  CUDA tensor without `.cpu()` (`sopa/segmentation/methods/_instanseg.py`, 2.2.12 and main).
  Report upstream; once fixed, give InstanSeg the GPU (`conf/gpu.config`) and size patches for
  GPU memory: an A40 has 48 GB, and on CPU 37 channels at 2000 px peak near 70 GB. Measure GPU
  peaks and warn against those, not `instansegMemoryGB`.
- **Segmentation-time area filtering is off by decision.** `min_area_pixels2 = null` means
  sopa's CLI uses 0. Filtering belongs after aggregation (2.2 item 2). Note:
  `sopa/cli/resolve.py` takes `min_area` in µm², the segmentation CLI in px².
- **Resource profiles are estimates** except `size_tiny`; rewrite from large-slide runs (`-with-tower`).
- **H&E is not supported**; only `ome_tif` mIF input.

### Tooling

- **Local Mac test profile for the partial path.** Ashlar, backsub, sopa, Cellpose and InstanSeg
  run under `docker,emulate_amd64,laptop`; BaSiCPy and Coreograph do not (no AVX under
  Rosetta). A real-data test without those two would catch tool behaviour before the cluster.
  Use a one-patch crop of exemplar-001: stubs cover the wiring, and Cellpose-SAM takes 40 to
  55 min per 1600 px patch under Rosetta. See [CONTRIBUTING](docs/CONTRIBUTING.md#on-the-mac).
- **`bin/set_channel_names.py` element selection is untested.** Make it a pure function; test it.
- **nf-metro.** 2.1.0 renders the `ASHLAR -->|backsub| QC_METRICS` edge that 1.1.0 could not,
  but fails on the current map without it. Add the edge, pin 2.1.0, check the SVG by eye. Until
  then re-render with `nf-metro==1.1.0`, which is pinned nowhere.
- **Offer upstream to sopa** (decisions.md, Segmentation): `--image-key` for staining
  segmentation, then drop `bin/segment_patch.py`; hole-aware rasterize; chunk-edge mask origin.

### From 2.0

- **Repair geometry once in `RESOLVE`** (`make_valid`, polygonal parts), so `{m}_cells` and
  `{m}_nuclei` areas agree with the linking's; `LINK_COMPARTMENTS`' repair becomes a safety net.
- **`uns['segmentation']` records the requested spec**, not sopa's defaults filled in later.
- **Tests to add:** a TMA slide report gets only its own method's cores; two samples through
  `SEGMENTATION` (store re-attached to the wrong sample).
- **`WRITE_SEGMENTATIONS` clears old elements before parsing the new ones**; a retry recovers.
- **The writer re-consolidates metadata only when it removed something**: a narrow kill window.
- **An unhashable key in a `*_kwargs` string** fails with an error that does not name the param.
- **The nf-core `BACKSUB` stub writes an empty marker sheet**: no stub run of exemplar-002.
  Candidate `nf-core modules patch`.
- **A user table annotating a removed reserved shape is left dangling.**
- **`QC_METRICS` repeats the image histograms per method**; once per sample would do.

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
  `nf_core_version` in `.nf-core.yml` says 4.2.0 so CI lints with the tools we use locally;
  the template files are still 4.0.3's.
