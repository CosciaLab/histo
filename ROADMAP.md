# Roadmap

The tracker for this project; GitHub Issues is not used. Reasoning is in
[docs/decisions.md](docs/decisions.md), larger ideas in [docs/future-ideas.md](docs/future-ideas.md).

Priorities, in order: transparency, robustness, troubleshootability. Sizes are focused working
time, estimated before the release; treat them as rough.

## Status

| Phase                  | State                                                         |
| ---------------------- | ------------------------------------------------------------- |
| 0. Freeze and diagnose | Done                                                          |
| 1. Scaffold            | Done: from nf-core/sopa, rebranded, out-of-scope parts cut    |
| 2. Preprocessing       | Done: BaSiCPy, Ashlar, backsub, Coreograph                    |
| 3. TMA path            | Done: per-core processing, per-slide merge and QC page        |
| 4. Resource profiles   | Done: `size_tiny`/`small`/`medium`/`huge`, `slurm`            |
| 5. Containers          | Done: 7 images, manifest, pre-staging documented              |
| 6. Testing             | Done; exemplar releases checked by hand on the cluster        |
| 7. QC report           | Metrics, images and reports in; thresholds need more slides   |
| 8. Releases            | 1.0.0 on 2026-10-06, 1.1.0 on 2026-10-09, 1.2.0 on 2026-10-21 |

## Verified on real data

- mIF, 3 cycles, 12 channels: 9,855 cells.
- TMA, 2 cycles: 4 cores, processed independently, merged to 29,574 cells.
- 10-cycle TMA, with and without backsub.
- Tiling: 9,855 cells as one patch versus 9,896 across six (0.4%).
- WSI, 3 cycles, 15 channels (5 background), 21,798 x 11,295 px, backsub: 142,493 cells in 72
  patches. All Phase 7 metrics and thresholds are calibrated on this one run.
- Release candidate `3717ea0`, 2026-10-06, by `nextflow run`: exemplar-001 9,877 cells;
  exemplar-002 with 2 and with 10 cycles, identical per-core counts (7,472, 4,779, 7,604, 9,678).
  These are the exemplar test baselines.

Memory: 8.7 GB peak RSS in `BASICPY` on the WSI run; 1.7 GB peak across 49 tasks on the
smaller runs. `TO_SPATIALDATA` reported exactly 8.00 GiB, likely a ceiling, so treat it as
unmeasured.

## Next releases

Segmentation, then quantification, then learned features. Each release adds its own chapter
to the HTML QC report; MultiQC suits tool logs, not our figures.

### 1.2.1: StarDist fix

1. **QC_IMAGES fails with StarDist.** `read_boundaries` (`bin/qc_images.py:76`) assumes
   `cellpose_boundaries`. Pass the backend's key; add a StarDist stub test.

### 1.3: segmentation input

1. **Three-channel projection** for CPSAM and InstanSeg: split `use_projection`'s `cell`
   channel into membrane and cytoplasm.
2. **Report chapters**, one per stage.

### 1.4: segmentation backends

1. **Cellpose-SAM.** sopa 2.2.9 selects `cpsam` under cellpose ≥ 4. Needs a cellpose 4
   image and a check of what `--diameter` means for cpsam. 3–5 days. `use_projection` needs
   no change: Cellpose-SAM takes its two channels as they are.
2. **InstanSeg.** No need to wait for sopa: `sopa.segmentation.custom_staining_based` should
   run any per-patch method (verify the API). Gives nuclei and cells.
3. **GPU on SLURM**: `process_gpu` is unused; CPSAM on CPU is too slow for a WSI.
4. **Pre-staged weights**, for every backend. `CELLPOSE_LOCAL_MODELS_PATH` points at an empty
   directory (`patch_segmentation_cellpose/main.nf:19`), so every task downloads weights.
   Bump sopa to 2.2.11 for `sopa download cellpose --model-dir`. ~1 day.
5. **`PATCH_SEGMENTATION_CELLPOSE` CPUs**: `process_single`, but used 133%.

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

[Future idea 5](docs/future-ideas.md). Spike first: does Coreograph find the same cores on a
stage-position mosaic? If not, stop. It changes the preprocessing outputs, so it ships in 2.0.

### 2.0: breaking changes only

1. **Reject `technology` and `aggregate_channels`.** Ignored with a warning since 1.2; drop the
   `deprecated` map in `rejectUnknownParams`, so they become unknown parameters.

## Before every release

Two runs on the cluster, by hand. Images are 8.8 GB (mIF) to 14.7 GB (with Coreograph),
too large for GitHub runners.

```bash
export HISTO_EXEMPLARS=/fast/AG_Coscia/$USER/HISTO/exemplars
bash tools/fetch_exemplars.sh          # 1.1 GB, public mcmicro S3, no credentials

export TMPDIR=/fast/AG_Coscia/$USER/tmp && mkdir -p "$TMPDIR"
export NXF_TEMP="$TMPDIR" NXF_OPTS="-Djava.io.tmpdir=$TMPDIR" NXF_OFFLINE=true

nf-test test tests/exemplar001.nf.test --profile test_exemplar001,singularity,size_small,slurm
nf-test test tests/exemplar002.nf.test --profile test_exemplar002,singularity,size_small,slurm

uvx --from nf-core nf-core pipelines lint --release
```

What each covers is in [tests/README.md](tests/README.md). If nf-test is blocked on the
cluster, `nextflow run` with the same profiles and an `--outdir` is enough. Cell counts must stay
within ±2% of the baselines above. Nothing checks `use_preprocessing = false` on real data (stub
only) or StarDist.

## Longer term

Costs and risks in [docs/future-ideas.md](docs/future-ideas.md). The marker sheet already has
the columns these need (`channel_role`, `exposure`, `background`, `filter`).

1. **Ashlar registration QC: thresholds.** The fork's `--qc-output` is in the reports; what
   counts as bad still needs exemplar-001, exemplar-002 and a real slide behind it.
2. **Imaging QC.** Saturation per channel is under a day (the histograms exist). Focus and
   artefacts are open-ended and need labelled examples. 5–10 days.
3. **Read `.czi` metadata** for backsub exposure. `bioio_bioformats` is already in the BaSiCPy
   image, so no new container. `.czi` channel names are dyes, not markers: they can check the
   `filter` column, not name channels. Sheet values always win. 1–2 weeks.
4. **Dearray across every nuclear channel** to detect cores lost between cycles. One Coreograph
   call per `dna` channel; each writes every core again, so disk grows with cycles. 1–1.5 weeks.
5. **H&E input.** Separate path: no preprocessing, StarDist's H&E model, morphology features,
   no QC at first. May need a new image for a WSI reader. 3–5 weeks.

## Open

### Findings

- **Leiden clusters are not reproducible on our one slide.** Best seed-to-seed ARI across
  resolutions 0.1 to 2.0 was 0.596, against a 0.9 floor; the report says so. Recheck on a
  second slide. Also test whether `n_iterations=2` (`bin/qc_images.py:362,379`) causes part of
  it. If it holds, show clusters as a staining summary or switch to gating.
- **Silhouette does not work for choosing Leiden resolution.** It falls monotonically with
  resolution, so it always picks the coarsest. Still reported; selection uses seed stability.
- **Every `-stub` run warns about a positional argument `true`.** Nextflow 26.04.6 leaves it in
  the args for both `-stub` and `-stub-run`. Harmless.

### Known limitations

- **Cellpose downloads its weights at run time** (1.4 item 4).
  Segmentation fails without network.
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
