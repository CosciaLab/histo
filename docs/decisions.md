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
and points sopa's `cell_segmentation_image` attribute at it; patchify, segmentation and resolve
follow that attribute. `DROP_PROJECTION` deletes it before `AGGREGATE`, so quantification reads
every marker and the published store has one image, as without projection.

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
automatic value would make the same slide segment differently on different hardware. See
[usage.md](usage.md).

**Size profiles are one file**, `conf/sizes.config`, with its own `profiles` scope.

**Tiled segmentation is not scaled by size profile.** Its cost follows `patch_width_pixel`. A
larger slide means more tasks, not bigger ones.

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
