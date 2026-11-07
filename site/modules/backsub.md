# backsub: background subtraction

## What it does

Tissue autofluorescence adds to every marker. backsub subtracts, pixel by pixel, a channel
acquired only to record that background from the markers you assign it to.

% source: https://github.com/SchapiroLabor/Background_subtraction#introduction

## Parameters

- [`use_backsub`](../inputs/parameters-full.md#use_backsub): turns the step on. Off by default.
- [`backsub_args`](../inputs/parameters-full.md#backsub_args): extra options handed to backsub.
- Three [marker sheet](../inputs/markers.md) columns: `exposure` (every channel),
  `background` (which `autofluorescence` channel to subtract from this marker) and `remove`
  (drop this channel afterwards). They are checked when the run starts.

More in [Background subtraction](../inputs/parameters.md#background-subtraction).

% source: nextflow_schema.json:72-83
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:316-345

## How it works

Each marker channel loses its background channel, scaled by the two channels' exposure times:

```text
marker_corrected = marker_raw − background × (exposure_marker / exposure_background)
```

Channels marked `remove`, usually the background channels themselves, are then dropped. backsub
was developed for Lunaphore COMET data and works with MCMICRO.

% source: https://github.com/SchapiroLabor/Background_subtraction#readme

:::{note} Figure pending
One marker channel before and after subtraction, with its autofluorescence channel, from the
WSI background-subtracted exemplar run.
:::

It runs once per sample after [Ashlar](ashlar.md), or once per core after
[Coreograph](coreograph.md). The image before subtraction is kept for the QC report, which
compares the two.

% source: subworkflows/local/preprocess_images/main.nf:111-137

**Inputs and outputs.** In: the stitched OME-TIFF and the marker sheet. Out, under
`preprocessing/background_subtraction/`: `{sample}_backsub.ome.tif`, a pyramidal OME-TIFF, and
`{sample}_backsub.csv`, a marker sheet that matches it. Everything downstream reads this new
sheet: removed channels are gone and `channel_number` is renumbered. See
[Preprocessing outputs](../outputs/preprocessing.md).

% source: docs/output.md#preprocessing
% source: CHANGELOG.md:362-368

## Similar tools

- **Subtracting after quantification**: measure the autofluorescence channel per cell like any
  marker, and correct the table instead of the image. backsub's authors encourage this when the
  corrected image is not needed for viewing or segmentation.
- **Background estimators** such as a rolling-ball filter remove smooth background from a single
  channel, without a recorded autofluorescence channel.

backsub came as an optional step with the preprocessing half from nf-core/mcmicro.

% source: https://github.com/SchapiroLabor/Background_subtraction#introduction
% source: README.md#what-this-is

## Read more

- backsub has no paper: [SchapiroLabor/Background_subtraction](https://github.com/SchapiroLabor/Background_subtraction).
- MCMICRO, the pipeline it works with: [@doi:10.1038/s41592-021-01308-y].
- [Tutorial: a whole slide with background subtraction](../tutorials/wsi-backsub.md).

Version used:

```{include} ../_generated/modules/backsub.md

```
