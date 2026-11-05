# Channel projection

## The idea

Cellpose takes a nuclear and a cell channel. In a multiplex panel, cell boundaries are spread over
many markers, each present on some cell types only. Projection builds the two channels from the
marker sheet, so Cellpose sees every relevant marker; quantification still reads every marker on
its own.

% source: docs/usage.md#two-channel-segmentation-use_projection

For each output channel, every marker in its group is:

1. rescaled to 0–1 between its own low and high percentile (1st and 99.9th by default), with
   pixels of exactly 0 left out;
2. smoothed with a Gaussian (σ = 1 px by default);
3. combined with the group's other markers, pixel by pixel, by maximum (or mean).

The groups come from the marker sheet's `segmentation` column if it has any value. Otherwise
`nuclear` is the first `dna` channel, and `cell` is every `marker` whose `channel_compartment`
includes membrane or cytoplasm.

% source: bin/project_channels.py:1-11
% source: bin/project_channels.py:37-82
% source: conf/modules.config:94-110

:::{note} Figure pending
The projection preview, nuclear in magenta and cell in green, from
`qc/{sample}_projection.png` of an exemplar-001 run with `use_projection`.
:::

## Why this pipeline uses it

The defaults come from a benchmark on two crops with Cellpose 3 and Cellpose-SAM, judged by eye
with metrics as support; there was no ground truth.

- **Maximum, not mean.** Mean dims markers found on one cell type: Cellpose-SAM then missed a
  whole lymphocyte cluster (72 % of nuclei inside a cell, against 95 % with maximum).
- **Projection beats DNA alone.** On exemplar-001, at Cellpose's own thresholds, nuclei inside a cell rose from 86 % to 99 %,
  and CD45-positive pixels inside a cell from 65 % to 84 %.
- **Zeros are left out of the percentiles.** Ashlar pads unregistered areas with zeros; counting
  them put the floor below the background, and one low-range marker then lit up the glass.
- **Nuclear is the first `dna` channel**: Ashlar's reference, the best registered, and free of
  the cell loss later cycles show.

% source: docs/decisions.md#channel-projection

## In this pipeline

```{include} ../_generated/modules/projection.md

```

- `PROJECT_CHANNELS` runs after tissue segmentation and before the patches. It adds an image
  element `<image>_projected` with channels `nuclear` and `cell`, written as 16-bit integers.
- Only [Cellpose](cellpose.md) reads it. [InstanSeg](instanseg.md) and
  [quantification](quantification.md) read the full image.
- `WRITE_SEGMENTATIONS` deletes it at the end, unless `keep_projection`.
- Percentiles are taken on a coarse pyramid level, at least 2000 px on its long side, so the cost
  does not grow with the slide.
- It writes `qc/{sample}_projection.png` and `.json`: what Cellpose saw, and each marker's share
  of pixels in which it is the brightest. A marker brightest in over half of its channel is listed
  as `dominant`, and the log warns. See [output](../reference/output.md#qc-report).

% source: workflows/histo.nf:90-99
% source: docs/decisions.md#channel-projection
% source: bin/project_channels.py:1-35
% source: conf/modules.config:94-110
% source: docs/output.md#qc-report

What steers it:

- [`use_projection`](../reference/parameters.md#use_projection): needs `use_cellpose` and
  `use_preprocessing`, with `cellpose_channels` unset.
- [`keep_projection`](../reference/parameters.md#keep_projection): keep `<image>_projected` in the
  published store, to view beside the cell outlines.
- [`projection_method`](../reference/parameters.md#projection_method),
  [`projection_low_percentile`](../reference/parameters.md#projection_low_percentile),
  [`projection_high_percentile`](../reference/parameters.md#projection_high_percentile) and
  [`projection_sigma`](../reference/parameters.md#projection_sigma).

% source: nextflow_schema.json:343-387
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-686

## Caveats

- **Set the Cellpose thresholds when projecting.** sopa's defaults tile the whole tissue into
  cells whatever the projection shows; see
  [Two-channel segmentation](../reference/usage.md#two-channel-segmentation-use-projection).
- **One marker can swamp a channel.** A diffuse, bright cytoplasm marker can make Cellpose miss
  whole groups of cells. Check `dominant` and the preview first when cells look wrong, and leave
  the marker out with the `segmentation` column.
- **`-resume` after the projection was deleted** fails with "projection removed by an earlier
  run". Rerun without `-resume`, or set `keep_projection`; see
  [-resume and the store](../reference/usage.md#id-resume-and-the-store).
- **On hazy raw images**, `projection_low_percentile: 50` removes the haze from the cell channel.

% source: docs/usage.md#two-channel-segmentation-use_projection
% source: docs/usage.md#-resume-and-the-store
% source: bin/segment_patch.py:60-70

## Read more

- How the defaults were chosen:
  [decisions.md](https://github.com/CosciaLab/histo/blob/dev/docs/decisions.md#channel-projection)
  and `tools/benchmark_projection.py`.
