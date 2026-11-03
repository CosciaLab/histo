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
  projection (cells cover 94 to 96% of the crop). Cellpose's 0.4 and 0 with CLAHE off follow
  membranes. Documented, not defaulted, since changing them would change runs without
  projection.
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

**GPU through one switch, `use_gpu`.** It sets Nextflow's `accelerator` on Cellpose patch tasks,
and `SEGMENT_PATCH` derives the device from it, so the two cannot disagree. InstanSeg stays on
CPU until sopa's wrapper works on CUDA (ROADMAP).
The SLURM executor ignores `accelerator`, so `slurm` and `mdc` translate it into `--gres`. MDC asks
for A40s: the sopa image's CUDA 13 has no V100 kernels, and only A40 nodes have Ceph. A CUDA check
fails the task, since cellpose falls back to CPU silently.

**Cellpose-SAM replaced Cellpose 3.** In the projection benchmark Cyto3 fell back to nuclei where
Cellpose-SAM found cells, at ~8x the time. `diameter` is fixed at 30, cpsam's training size, so
images are not rescaled.

## Segmentation

**One spec per method × target**, built once from params (`segmentationSpecs`), so a new
method is one more entry. Unset options keep sopa's per-method CLI defaults:
`StainingSegmentation`'s own would blur and equalise InstanSeg's input.

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

**Aggregation is copied from sopa 2.2.12, with two fixes.** sopa rasterizes the exterior only,
so a cytoplasm ring would be measured as the whole cell. And it places the mask of a cell crossing a
dask chunk edge at the cell's bounds, not the clipped window's: the mask is shifted, so 1.x
intensities of such cells were wrong (errors up to ~3600 units in review). Building the table
with `TableModel.parse` keeps the cell ids sopa's `parse_table` renumbers. Also: each part of a
MultiPolygon gets its own mask, OR-ed (an island in a lake survives); a synchronous dask
scheduler, as tasks add into shared arrays; NaN for an empty mask. Offer both fixes
upstream (ROADMAP).

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
