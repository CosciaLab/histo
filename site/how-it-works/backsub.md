# Background subtraction: backsub

## The idea

Tissue autofluorescence and background signal add to every marker channel. They can mislead
segmentation and inflate measured intensities. A channel acquired only to record that
background, an `autofluorescence` channel in the marker sheet, can be subtracted pixel by pixel.

% source: https://github.com/SchapiroLabor/Background_subtraction#introduction
% source: docs/usage.md#inputs

backsub subtracts, from each marker channel, the background channel the marker sheet names for
it, scaled by the two channels' exposure times:

```text
marker_corrected = marker_raw − background × (exposure_marker / exposure_background)
```

Channels marked `remove` are dropped from the output. backsub writes a pyramidal OME-TIFF and a
marker sheet that matches it. It was developed for Lunaphore COMET data and works with MCMICRO.

% source: https://github.com/SchapiroLabor/Background_subtraction#readme

:::{note} Figure pending
One marker channel before and after subtraction, with its autofluorescence channel, from the
WSI background-subtracted exemplar run.
:::

## In this pipeline

```{include} ../_generated/modules/backsub.md

```

- An optional step of the preprocessing half taken from nf-core/mcmicro, off by default.
- Runs once per sample after Ashlar, or once per core after Coreograph, so each core keeps its
  unsubtracted image and the QC report can compare before and after.
- backsub receives the marker sheet as written; columns it does not use pass through.
- Its own marker sheet replaces the input one for everything downstream: removed channels are
  gone and `channel_number` is renumbered.
- The unsubtracted image is passed on to QC.
- Outputs are `{sample}_backsub.ome.tif` and `.csv` under
  `preprocessing/background_subtraction/`; see [output](../reference/output.md#preprocessing).

% source: README.md#what-this-is
% source: subworkflows/local/preprocess_images/main.nf:111-137
% source: CHANGELOG.md:362-368
% source: docs/output.md#preprocessing

What steers it:

- [`use_backsub`](../reference/parameters.md#use_backsub): turns the step on.
- [`backsub_args`](../reference/parameters.md#backsub_args): extra arguments passed through to
  backsub.
- The [marker sheet](../reference/samplesheet.md#marker-sheet) columns `exposure`,
  `background` and `remove`.

% source: nextflow_schema.json:72-83
% source: docs/usage.md#inputs

## Caveats

- **The marker sheet is checked at startup**; see [Inputs](../reference/usage.md#inputs) for
  the `exposure`, `background` and `remove` rules.
- **Subtracting images is not the only option.** backsub's authors encourage subtracting
  autofluorescence after quantification instead, when the corrected image is not needed for
  viewing or segmentation.

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:316-345
% source: https://github.com/SchapiroLabor/Background_subtraction#introduction

## Read more

- backsub has no paper: [SchapiroLabor/Background_subtraction](https://github.com/SchapiroLabor/Background_subtraction).
- MCMICRO, the pipeline it works with: [@doi:10.1038/s41592-021-01308-y].
