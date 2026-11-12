# Nimbus: marker positivity per cell

## What it does

Nimbus gives every cell a score between 0 and 1 for every marker. A score near 1 means the model
sees the marker as positive in that cell. You do not set a threshold per marker.

% source: doi:10.1038/s41592-025-02826-9
% source: modules/local/nimbus/main.nf

## Parameters

- [`use_nimbus`](../inputs/parameters-full.md#use_nimbus): turns Nimbus on.
- [`pixel_size`](../inputs/parameters-full.md#pixel_size), required: your image's pixel size in µm.
  Nimbus rescales the image with it, so the pipeline stops at startup without it.
- [`segment_cells`](../inputs/parameters-full.md#segment_cells), required: Nimbus was trained on
  whole cells, so nucleus-only runs are refused.
- [`nimbus_channels`](../inputs/parameters-full.md#nimbus_channels): the markers to score. By
  default, every `marker` channel of the [marker sheet](../inputs/markers.md). Required for a
  stitched image you bring yourself, which has no marker sheet.
- [`use_gpu`](../inputs/parameters-full.md#use_gpu): recommended. A CPU gives the same scores but
  takes hours per whole slide.

% source: nextflow_schema.json
% source: docs/decisions.md#learned-features

## How it works

For each marker, Nimbus takes that channel and a mask of the cells, and predicts for every pixel
how likely the marker is positive. A cell's score is the mean over its pixels.

Each channel is first divided by its 0.999 quantile, then clipped to 0 to 1. The quantile is taken
per image, or per core on a tissue microarray. Per core keeps differences between patients, but a
core with no positive cells can score noise as signal.

Large images are cut into [tiles](tiling.md) with a margin of surrounding context, so memory does
not grow with the image. Tiling can shift scores: on a test crop at 0.65 µm/px, tiled and whole-image
scores differed by up to 0.41 (mean 0.011), while a crop at 1 µm/px showed no difference. Scoring the
whole image at once matched the Nimbus authors' own code to within 1e-6 at both pixel sizes.
Test-time augmentation, which averages the model's answer over flipped copies of the input, is
always on, with the same setting on CPU and GPU. We have not yet compared CPU and GPU scores.

% source: docs/decisions.md#learned-features
% source: bin/nimbus_cells.py

**Inputs and outputs.**

| In                                   | Out                                                     |
| ------------------------------------ | ------------------------------------------------------- |
| The full image, one marker at a time | A table `{method}_nimbus` in the store, in `tables/`.   |
| The cells of one segmentation method | One row per cell, one column per marker, values 0 to 1. |
| `pixel_size`                         | A JSON file of settings in `learned_features/`.         |

A column is empty (NaN) for a marker with no signal anywhere in the image. See
[The SpatialData store](../outputs/zarr.md).

% source: docs/output.md#nimbus-scores

## Open points

- The model's magnification is set from your pixel size as `10 / pixel_size`. The authors never say
  what "10x" means in µm per pixel, so this is provisional and may change.

% source: docs/decisions.md#learned-features

## Read more

- Nimbus: [@doi:10.1038/s41592-025-02826-9].
- [Nimbus on GitHub](https://github.com/angelolab/Nimbus-Inference). Code and weights are MIT.

Version used:

```{include} ../_generated/modules/nimbus.md

```
