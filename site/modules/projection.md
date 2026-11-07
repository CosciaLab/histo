# Channel projection

## What it does

Cellpose looks at two images: a nuclear stain and a cell stain. Projection builds that cell image
from all the membrane and cytoplasm markers of your panel, so Cellpose sees every cell type, not
only those one marker labels.

% source: docs/usage.md#two-channel-segmentation-use-projection
% source: bin/project_channels.py:1-11

## Parameters

- [`use_projection`](../inputs/parameters-full.md#use_projection): turns it on. Needs
  `use_cellpose`, and the pipeline must stitch the image (it reads the marker sheet); leave
  `cellpose_channels` unset.
- [`keep_projection`](../inputs/parameters-full.md#keep_projection): keep the projected image in
  the store, to view it under the cell outlines.
- [`projection_method`](../inputs/parameters-full.md#projection_method): combine markers by
  maximum (default) or mean.
- [`projection_low_percentile`](../inputs/parameters-full.md#projection_low_percentile) and
  [`projection_high_percentile`](../inputs/parameters-full.md#projection_high_percentile),
  default 1 and 99.9: each marker's brightness range.
- [`projection_sigma`](../inputs/parameters-full.md#projection_sigma), default 1 px: smoothing.
- The [marker sheet](../inputs/markers.md) decides which marker goes where; see below.

More in [Many markers with Cellpose](../inputs/parameters.md#many-markers-with-cellpose).

% source: nextflow_schema.json:343-387
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-686

## How it works

For each of the two output images, `nuclear` and `cell`, every marker in its group is:

1. rescaled to 0–1 between its own low and high percentile, with pixels of exactly 0 left out;
2. smoothed with a Gaussian;
3. combined with the group's other markers, pixel by pixel, by maximum (or mean).

The groups come from the marker sheet's `segmentation` column if any row has a value. Otherwise
`nuclear` is the first `dna` channel, and `cell` is every `marker` whose `channel_compartment`
includes membrane or cytoplasm.

% source: bin/project_channels.py:1-11
% source: bin/project_channels.py:37-82
% source: conf/modules.config:94-110

:::{note} Figure pending
The projection preview, nuclear in magenta and cell in green, from
`qc/{sample}_projection.png` of an exemplar-001 run with `use_projection`.
:::

Only [Cellpose](cellpose.md) reads the projection. [InstanSeg](instanseg.md) and
[quantification](quantification.md) read the full image, so every marker is still measured on its
own.

% source: docs/decisions.md#channel-projection

**Inputs and outputs.** In: the image in the [SpatialData store](spatialdata.md) and the marker
sheet. Out: an image `<image>_projected` with two channels, `nuclear` and `cell`, deleted at the
end unless `keep_projection`; and a preview, `qc/{sample}_projection.png`, with a
`qc/{sample}_projection.json` that lists each marker's share of the pixels in which it is the
brightest. A marker brightest in over half of its image is listed as `dominant`, and the log
warns: it may be hiding the others. See [QC files](../outputs/qc.md).

% source: workflows/histo.nf:90-99
% source: bin/project_channels.py:1-35
% source: docs/output.md#qc-report

## Similar tools

- **Pick one membrane marker**, as `cellpose_channels` does: simple, but cells without that
  marker are missed or drawn from the nucleus alone.
- **Sum or average the markers**: averaging dims markers found on one cell type only.
- **[InstanSeg](instanseg.md)** reads every marker itself, with no projection.

The defaults come from a benchmark on two crops with Cellpose 3 and Cellpose-SAM, judged by eye
with metrics as support; there was no ground truth.

- **Maximum, not mean.** With mean, Cellpose-SAM missed a whole lymphocyte cluster (72 % of nuclei
  inside a cell, against 95 % with maximum).
- **Projection beats DNA alone.** On exemplar-001, nuclei inside a cell rose from 86 % to 99 %,
  and CD45-positive pixels inside a cell from 65 % to 84 %.
- **Zeros are left out.** Stitching pads unregistered areas with zeros; counting them put the
  floor below the background, and one dim marker then lit up the glass.
- **Nuclear is the first `dna` channel**: the stitching reference, the best aligned, and free of
  the cell loss later cycles show.

% source: docs/decisions.md#channel-projection

## Read more

- How the defaults were chosen:
  [decisions.md](https://github.com/CosciaLab/histo/blob/dev/docs/decisions.md#channel-projection)
  and the
  [benchmark script](https://github.com/CosciaLab/histo/blob/dev/tools/benchmark_projection.py).
- [Tutorial: multiple segmentations](../tutorials/multiple-segmentations.md).

Version used:

```{include} ../_generated/modules/projection.md

```
