# Decisions

Why the pipeline is built the way it is. Each entry settles a question that would otherwise
be asked again.

## Architecture

**Two upstream projects, one handoff.** Preprocessing from nf-core/mcmicro, segmentation onward
from nf-core/sopa, meeting at a stitched OME-TIFF. sopa tiles segmentation, so it is size
independent; with 5–100 GB inputs that outranks everything else.

**Cloned, not forked.** sopa was imported at `c2b4e5f` with fresh history, verified
byte-identical by tree hash before any change.

**Not an nf-core pipeline**, but follows its conventions. Template divergences are listed in
`.nf-core.yml`.

## The TMA path

**Merge at the very end.** Each core runs the whole downstream half alone. Many small dense
objects segment better than one large sparse one, and per-core QC survives.

**`MERGE_SPATIALDATA` writes one element at a time**, so peak memory is one core, not all of
them (614 MB for four cores).

**An unreadable core is a hard failure.** The predecessor warned and continued, so a slide
could merge 78 of 80 cores and exit 0.

**Elements are named `{core_id}__{original}`**, skipping the prefix if already present. The
double underscore is because core IDs contain single ones.

## Channel names

Ashlar writes no marker names, backsub writes them, Coreograph drops them. sopa then reads the
OME channel IDs, giving columns like `Channel:0:0`.

**Fixed in the Zarr after conversion.** `SET_CHANNEL_NAMES` writes them from the marker sheet
into about 5 KB of group metadata, free at any image size. `AGGREGATE` inherits them.

**The OME-TIFF is left alone.** A task must not mutate its staged input (a symlink into the
upstream work directory, which `-resume` relies on), so it would mean copying the whole image.

**Check the property, not a proxy.** The old guard grepped sopa's log for a message that only
fires when no names are found. It never fired, since sopa found the IDs.

## Pixel size

Not in the Zarr. SpatialData's option, an extra coordinate system, is a poor fit, and
redefining `global` would silently make `patch_width_pixel` and `min_area_pixels2` microns.
Images stay in pixels; Ashlar keeps `PhysicalSizeX` in the OME-TIFF.

## Channel projection

**A transient image element, not a new OME-TIFF.** `PROJECT_CHANNELS` adds `<image>_projected`
beside the full image; Cellpose specs name it as their image (see Segmentation), and
`WRITE_SEGMENTATIONS` deletes it unless `keep_projection`. Quantification reads the full image.

**QC names its image.** It reads the element named by `cell_segmentation_image`, not the store's
only image, so a store can hold others: a kept projection now, a pre-backsub image later.

**Nuclear is the first `dna` channel by default**, the Ashlar reference: best registered, and
free of the cell loss later cycles show.

**Zeros are left out of the percentiles.** Ashlar pads unregistered areas with them; counting
them put the floor below the background, and one low-range marker then lit up the glass.

**Defaults from a benchmark**, `tools/benchmark_projection.py`, Cellpose 3 `cyto3` and
Cellpose-SAM. Two crops: exemplar-001 (0.65 µm/px, 8 cell markers) and an in-house 15-channel
panel (0.35 µm/px, raw). No ground truth; outlines were judged by eye, with metrics as support.

- **Maximum, not mean.** Mean dims markers found on one cell type: Cellpose-SAM then missed a
  whole lymphocyte cluster (72% of nuclei in a cell, 95% with max); Cyto3 fell back to nuclei.
- **Low percentile 1.** 50 changed little once zeros were excluded; it helps hazy raw images.
- **Thresholds matter more than projection.** sopa's `flow_threshold: 2`,
  `cellprob_threshold: -6` and CLAHE 0.2 tile the tissue into cells with or without
  projection (cells cover 94 to 96% of the crop). The segmentation benchmark set new ones.
- **Projection over DNA only**, both at Cellpose thresholds, exemplar-001: nuclei inside a cell
  rose from 86% to 99%; CD45-positive pixels inside a cell from 65% to 84%.
- Cellpose-SAM took about 24 s per 1200 px crop on Apple MPS, against 3 s for `cyto3`.

## Parameters

**`patch_width_pixel` is not computed for you.** It changes results at patch boundaries, so an
automatic value would make the same slide segment differently on different hardware. The fixed
default, 2000 px, is well below sopa's 5000 to keep InstanSeg's memory down: 37 channels need 78 GB
at 2000 px and 171 GB at 3000. See
[usage.md](usage.md).

**InstanSeg memory is computed from the patch**, not set per size profile: it grows with channels
times patch area. Per megapixel it is flat up to about 4 channels, then ~0.25 GB per channel: on
one exemplar core, 2 channels peaked at 15 GB and 37 at 130 GB. See `instansegMemoryGB`.

**Size profiles are one file**, `conf/sizes.config`, with its own `profiles` scope.

**Tiled segmentation is not scaled by size profile on CPU.** Its cost follows `patch_width_pixel`.
GPU tasks are, as a stopgap: larger slides usually get larger patches. A tile-size benchmark
replaces both (ROADMAP).

**GPU through one switch, `use_gpu`.** It sets Nextflow's `accelerator` on Cellpose and InstanSeg
patch tasks, and `SEGMENT_PATCH` derives the device from it, so the two cannot disagree. InstanSeg
on GPU is capped at 10 channels, checked at startup, until its GPU memory is measured (ROADMAP).
The SLURM executor ignores `accelerator`, so `slurm` and `mdc` translate it into `--gres`. MDC asks
for A40s: the sopa image's CUDA 13 has no V100 kernels, and only A40 nodes have Ceph. A CUDA check
fails the task, since cellpose falls back to CPU silently.

**Cellpose-SAM replaced Cellpose 3.** In the projection benchmark Cyto3 fell back to nuclei where
Cellpose-SAM found cells, at ~8x the time. `diameter` is fixed at 30, cpsam's training size, so
images are not rescaled. `cpsam_v2` is the default, following the cellpose developers; it is not
benchmarked against `cpsam`.

## Segmentation

**One spec per method × target**, built once from params (`segmentationSpecs`), so a new
method is one more entry. Unset options keep sopa's per-method CLI defaults, except Cellpose's
thresholds and preprocessing (Segmentation benchmark, below): `StainingSegmentation`'s own would
blur and equalise InstanSeg's input.

**One writer per store.** `sopa resolve` and `sopa aggregate` write into the store, and parallel
writers race on its root metadata: last writer wins, silently. So patch, resolve, link and
aggregate tasks read the store and write files; `WRITE_SEGMENTATIONS` alone writes them in.

**An explicit image key.** sopa's CLI segments the image named by `cell_segmentation_image`,
which two methods on two images cannot share. `segment_patch.py` passes `image_key` to
`StainingSegmentation` instead of flipping the attribute. Ids are built on the attribute's image,
so a method's cells and nuclei share a prefix whatever image each segmented.

**Nuclei link to cells by geometry, after resolve.** Methods return nuclei and cells in separate
passes, so geometry is all they share, and only resolved shapes are final. A nucleus links to
the cell holding the largest share of its area if that share is at least 0.5, a constant; ties
go to the cell first in the frame. Nothing is dropped.

**Mask rasterising is copied from sopa 2.2.12, with one fix.** sopa rasterizes the exterior
only, so a cytoplasm ring would be measured as the whole cell. Here holes are cut, each
MultiPolygon part in its own mask, OR-ed, so one part's hole cannot erase another (an island in
a lake survives). Building the table with `TableModel.parse` keeps the cell ids sopa's
`parse_table` renumbers. Empty mask: NaN. Offer the fix upstream (ROADMAP).

**NaN is "not measured", 0 "measured, nothing there".** A cell without a nucleus has NaN layers
and `cytoplasm_area`; a cell its nuclei fill has `cytoplasm_area` 0.

**Invalid polygons are repaired only where geometry is combined**, linking and comparison, with
`make_valid`, counted in the log. Stored shapes are what the method produced; a long unattended
run should not die on a vectorisation nit.

**A segmentation that resolves to nothing fails the run**, naming the spec, as an unreadable core
does. On a TMA one empty core stops the slide: loud, not silent.

**Numbers from the command line are parsed where used** (`toNumber`). Nextflow passes them as
Strings and params cannot be reassigned: `"3000" * 0.65` is string repetition, and a String in
the kwargs JSON fails sopa in every patch task.

**StarDist was sunset in 2.0.** Cellpose and InstanSeg segment nuclei.

## Segmentation benchmark

Cellpose's defaults come from `tools/segmentation_benchmark`: 475 settings of `cpsam_v2` scored
by F1 at IoU 0.5 against manual outlines. Data: Cross-platform mIF (119 Vectra and 10 CODEX
crops), TissueNet 1.1 test (1324 tiles) and 10 tonsil crops, partly annotated, used as a check
only. Deck and results: `3_Projects/Segmentation_Benchmark` (lab share).

- **No smoothing, no CLAHE.** Round 1 (168 settings): `projection_sigma`, `gaussian_sigma` and
  CLAHE 0.2 each lowered F1, and the smoothings add up; Cellpose-SAM normalises each patch itself.
  Round 2: CLAHE 0.01 also lost near good thresholds. Max and percentile 1 stay.
- **`flow_threshold: 0.6`, `cellprob_threshold: -1`.** Round 2 scored 7 × 8 pairs. Flow is flat
  from 0.6; on cellprob, Cross-platform nuclei want -1 or less and TissueNet nuclei 0 or more.
  The pair is the one with the smallest largest shortfall from each target's own best, a rule set
  before the run: within 0.065 of the best for cells and nuclei on both datasets. Separate
  nuclear thresholds would gain about 0.02 and add two parameters.
- **Gain.** Cells on Cross-platform 0.53 to 0.73 (128 of 129 crops better), on TissueNet 0.60
  to 0.87; nuclei 0.42 to 0.80 and 0.39 to 0.76.
- **Leave autofluorescence out of the cell channel** (+0.012 F1, Vectra only); nuclear markers
  too (+0.004). The marker sheet already chooses, so this is advice, not code.
- **Open:** nuclear projection smoothing at -1 is untested (it helped at 0.4 / 0); percentiles
  were per crop, not per slide.

## Learned features

**A stage after segmentation, one table per model and method.** `LEARNED_FEATURES` runs after
`SEGMENTATION`, only when a model is enabled. `NIMBUS` writes files; `WRITE_FEATURES` alone writes
`{method}_nimbus` into the store, after `WRITE_SEGMENTATIONS`. Scores are a table, not a layer: a
layer must share `{method}_table`'s `var` (marker × statistic), and viewers colour cells by table.
Later models (KRONOS) add a flag and a spec.

**Tile windows are sized at model scale.** The image is resized by `pixel_size` before inference.
Tile: 2048 model px, each cell owned by the tile holding its centroid. Window: the tile grown to its
cells' bounds plus a margin of halo + 32 model px. The halo is measured from the loaded model, 96 px
for `V1.pt`. Minimum window: 1056 model px, so the valid-padding path is always taken. Neighbours
are rasterised too, since they shape the binary mask Nimbus sees; only owned cells are scored.

**Tiling is meant to change nothing Nimbus computes; at 0.65 µm/px it does, measurably.**

- The one global step, the per-channel factor, is computed once per store and shared by every
  window. A channel with no factor is never passed on, or Nimbus would fall back to the window's
  own quantile.
- BatchNorm runs in eval mode on fixed statistics, and test-time augmentation averages within one
  input. No statistic crosses windows.
- A margin of at least the halo gives every owned cell the receptive field of whole-image inference.
- Upstream uses reflect padding up to 1024 px and tile-and-stitch above it, with different results.
  The minimum window keeps every window on the valid path, as upstream whole-slide inference is.

Measured on exemplar-001 crops, scores in [0, 1], with the real model on CPU:

| Pixel size | Crop        | Whole image against upstream | Tiled against whole image (2 × 2 windows) |
| ---------- | ----------- | ---------------------------- | ----------------------------------------- |
| 1.0        | 1280 × 1280 | max 7.2e-07                  | max 0 (window origins on the 16 px grid)  |
| 0.65       | 2100 × 2100 | max 3.0e-08, mean 4.3e-09    | max 0.414, mean 0.0113 (origins off grid) |

The 1.0 tiling result is uninformative: its window origins are multiples of the model's 16 px
pooling period. At 0.65 the origins fall off that grid and some cells move by up to 0.41, so the
claim "tiling changes no score" does not hold there. Cause not yet found; fixing it is open work
(Task 11 follows up). The 0.65 test is marked xfail with these numbers.

**Normalisation is per store.** Per core on a TMA, per image otherwise. A slide-wide factor would
erase differences between patients' cores. The cost: a core with no positive cells has noise
stretched to [0, 1]. The factor is the exact 0.999 quantile of nonzero pixels over a fixed-stride
subsample, so it is deterministic. Slide-wide is a ROADMAP item. A channel with no nonzero pixel
is NaN and listed in `uns`.

**Test-time augmentation is fixed on, upstream code unchanged.** It is the Nimbus default, and
it is the same setting on CPU and GPU. CPU against GPU agreement is still to be measured on the cluster. Upstream functions (`prepare_binary_mask`,
`prepare_input_data`, `test_time_aug`, `segment_mean`) are called as `predict_fovs` calls them.

**Cells only.** Nimbus was trained on whole-cell masks, so `use_nimbus` requires `segment_cells`.

**One pixel size.** `pixel_size` serves InstanSeg and Nimbus. `instanseg_pixel_size` is deprecated,
and removed at the next major release.

**Weights are baked in.** `V1.pt` (MIT, from HF `JLrumberger/Nimbus-Inference`) is inside
`docker.io/josenimo/nimbus:0.0.5`, with `HF_HUB_OFFLINE=1`.

**Open: magnification.** The code sets `MODEL_UM_PER_PX = 1.0` in `bin/nimbus_cells.py`, treating Nimbus' "10x" as
1 µm/px; resize scale, window sizes and `magnification = 10 * MODEL_UM_PER_PX / pixel_size` all follow it. Upstream never defines it ([issue #61](https://github.com/angelolab/Nimbus-Inference/issues/61)),
and 10x is often 0.5 µm/px. Both are compared on real data before the default is chosen.

### VirTues

**Slide statistics over tissue pixels.** Intensities are capped at the 0.99 quantile, `log1p`
transformed and z-scored per marker, per slide, over tissue pixels (`use_tissue_segmentation` is
required). On a TMA every core of a slide shares them, unlike Nimbus's per-core factor, so cells
stay comparable across cores and patients. The released weights were trained with the cap per image
and mean and SD per dataset; per-slide statistics depart from that, and `virtues_stats` is the way
back to dataset-wide ones. Statistics come from integer histograms, equal to numpy's quantile on
the pooled pixels.

**A core with no tissue does not stop the run.** sopa writes no ROI when it finds no tissue; such a
store counts as zero tissue, with a warning, and its cells are still embedded. A slide with no tissue
at all stops, naming it. sopa keeps the ROI on its coarsest pyramid level, so it is mapped to image
pixels first.

**One task per store, every method at once.** The GPU pass does not depend on cell masks; only the
averaging into cells does, and it is repeated per method. Per-tile tasks are on the ROADMAP.

**One global crop grid, so tiles match upstream.** Upstream's crop grid (128 px every 42 px, padded
by 120 px) is built once on the whole padded image. A tile embeds every crop touching its cells, so
each cell sees upstream's crop set. Attention never crosses crops, and resampling weights depend
on global coordinates only, so tiles give identical rows to a whole-image run with exact arithmetic
(tested with a fake encoder). On an A40 the fp16 encoder is too: batch 32 vs 8 and tile 512 vs 2048
give identical rows (parity tool).

**ESM-2 without attention contacts.** Upstream's `embed` keeps every attention map (about 25 GB for
Ki-67); we skip them. The embeddings are the same.

**Embed only channels with a `uniprot_id`, never DNA.** No parameter: the sheet decides. Upstream
leaves DNA stains out, so a `dna` row with an ID is an error, and no Histone H3 mapping is made.

**Cells only; cell, square and tissue embeddings.** Like upstream, no nuclei. A square is kept at
30% tissue or more; the tissue embedding is the mean of the kept squares. Squares are shapes with a
table, and the tissue vector has no region, as one row per store does not map onto the tissue polygons.

**Float16, `sp32`.** Embeddings are stored as float16, half the size, and enough for 512 numbers
per cell. `sp32` is the authors' default and benchmarked model; it is CC BY-NC 4.0, so non-commercial
use only. `sp31` (MIT) and `imc14` are not wired in.

**GPU, preprocessing and pixel size required.** FlashAttention has no CPU path. A stitched input has
no marker sheet, so no UniProt IDs. The model runs at 1 µm/px. The whole run is then on GPU,
segmentation included, so outlines differ slightly from a CPU run.

**Weights and sequences are baked in.** `docker.io/josenimo/virtues:d2c25e1-2`: virtues `d2c25e1`,
spora-io `ef15868`, FlashAttention 2.7.4.post1, torch 2.5.1+cu124, ESM-2 `esm2_t30_150M_UR50D`,
human Swiss-Prot with isoforms (release 2026_04), `HF_HUB_OFFLINE=1`.

**Checked on an A40:** every cell within cosine 0.99999999 of upstream's code; repeat runs identical.

**Open:** usefulness on real data.

## Quantification

**Shapes are read in tile windows, not segmentation patches.** `patch_width_pixel` is tuned for
segmentation, patches need not overlap enough to hold a cell, and tying the two would make
a resource setting change the table. A shape belongs to the tile holding its centroid; the
window grows to its pixel bounds, so a giant shape enlarges only its tile's window. Each shape is measured
whole, so medians and SDs are exact and `tile_size` does not change results.

**The statistic menu is `mean`, `median`, `std`, `min`, `max`, `q25`, `q75`, `q90`; the default
is `mean,median,std`.** No benchmark ranks statistics for phenotyping, and the mean is the
baseline. `q99` is not offered: in a 50 px cell it is the max. Min is mostly background and max
a hot pixel or a bright neighbour, so both are QC signals, opt-in. `mean` is required, as QC
clusters on it.

**Morphology is computed on the polygons**, exactly, with no raster. Circularity depends on how
the polygon was made (sopa smooths) and is unstable below ~30 px², so compare it within one
method only.

**Pixel units.** Areas and lengths are px and px², as `area` was. Pixel size in the Zarr is
deferred (ROADMAP).

## Containers

**Nothing is pulled at run time.** A pull failing hours in wastes the run and the queue slot.
`containers.tsv` is kept current by a prek hook; see [CONTRIBUTING](CONTRIBUTING.md#containers).

**Ashlar runs from our own public image, `josenimo/ashlar`.** It is the only way to get
rotation correction, per-cycle last-channel alignment and machine-readable stitching QC; none
is in a bioconda release. The fork (`josenimo/ashlar`, branch `histo-qc`) merges upstream,
jmuhlich's `rotation-correction` and `qc-report`, and adds `--qc-output`. Its `Dockerfile` and
pinned `docker/constraints.txt` are versioned there, so the image can be rebuilt.

**Ashlar QC comes from Ashlar's own state, not its log.** No log line records a rejected pair
or a discarded tile, so the fork dumps the aligners before writing the mosaic.

**The cache check computes Nextflow's exact filename.** Matching on tool and version once
reported an image as cached under another URI's name, and Nextflow still went to the network.

## Testing

**Properties, not checksums.** Cellpose output shifts with version and hardware. Channel names,
element names and patch counts cannot drift; cell count gets ±2%.

**A stub run cannot detect an incomplete commit.** Nextflow reads the working tree, not what
git recorded. `tools/clone_check.sh` runs from a fresh clone.

## Recurring lessons

- Validation never watched to fail is not validation. An `assert` inside a channel operator is
  swallowed; use `error()`.
- Error messages often point away from the cause. `nextflow config . -profile X` quickly
  separates a profile that is not loading from a broken pipeline.
- Version-proofing one side of a coupling is half a job. The Coreograph patch handled both
  versions' extensions; the parser of its filenames did not, and `.ome` leaked into core IDs.
