# InstanSeg: cell segmentation

## What it does

InstanSeg draws an outline around every cell, or every nucleus, using all the markers of a
multiplex panel at once, however many there are.

% source: doi:10.1101/2024.09.04.611150
% source: modules/local/utils.nf:196-201

## Parameters

- [`use_instanseg`](../inputs/parameters-full.md#use_instanseg): turns InstanSeg on.
- [`instanseg_pixel_size`](../inputs/parameters-full.md#instanseg_pixel_size), required: your
  image's pixel size in µm. InstanSeg rescales the image to its model's resolution with it;
  without it, a run could finish with few or no cells, so the pipeline stops at startup instead.
- [`instanseg_channels`](../inputs/parameters-full.md#instanseg_channels): the markers it reads.
  By default, from the [marker sheet](../inputs/markers.md): `dna` and `marker` channels for
  cells, `dna` only for nuclei. Required for a stitched image you bring yourself, which has no
  marker sheet.
- [`segment_cells`](../inputs/parameters-full.md#segment_cells) and
  [`segment_nuclei`](../inputs/parameters-full.md#segment_nuclei): cells, nuclei or both.
- [`instanseg_model_type`](../inputs/parameters-full.md#instanseg_model_type) and
  [`instanseg_kwargs`](../inputs/parameters-full.md#instanseg_kwargs) for other models and options.
- [`patch_width_pixel`](../inputs/parameters-full.md#patch_width_pixel): memory grows with patch
  area times the number of markers; see [Patch size](../inputs/parameters.md#patch-size).
- [`use_gpu`](../inputs/parameters-full.md#use_gpu): at most 10 markers on a GPU, for now; see
  [GPU](../inputs/parameters.md#gpu).

More in [Methods and targets](../inputs/parameters.md#methods-and-targets).

% source: nextflow_schema.json:442-473
% source: nextflow_schema.json:388-406
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:646-655
% source: docs/decisions.md#parameters

## How it works

For every pixel the network predicts a **seed map**, the distance to the nearest object boundary,
and an **embedding**, a short vector describing where the pixel sits within its object. Seeds are
the local maxima of the seed map. For each seed, a small network compares every nearby pixel's
embedding with the seed's and outputs the probability that the pixel belongs to that object.
Seeds in the same object are merged, and each pixel goes to its most probable object. The authors
report at least 60 % less processing time than the most widely used methods
[@doi:10.48550/arXiv.2408.15954].

% source: doi:10.48550/arXiv.2408.15954

For multiplexed fluorescence, a front end called ChannelNet treats the markers as an unordered
set. Each marker passes through the same network, their features are pooled, and the result is a
fixed three-channel image, whatever the number or order of markers. Two branches then predict
nuclei and whole cells. Training images were resized to 0.5 µm per pixel
[@doi:10.1101/2024.09.04.611150].

% source: doi:10.1101/2024.09.04.611150

:::{figure} ../images/modules/instanseg-channelnet-fig1.jpg
:alt: A network diagram in which two marker channels pass through parallel branches joined by max pooling, and two examples showing eight marker channels, their three-channel summary and the resulting nucleus and cell masks.

(a) ChannelNet: each channel passes through the same network, and features are shared across
channels by max pooling, so the number and order of channels do not matter. (b) Two multiplexed
images: eight input channels, the three-channel representation, and the predicted nuclei and
cells. Reproduced from [@doi:10.1101/2024.09.04.611150], CC BY 4.0.
:::

The model is `fluorescence_nuclei_and_cells` unless you name another. Through sopa, InstanSeg
returns one target at a time, so nuclei and cells are two passes over every [patch](tiling.md).
Autofluorescence, blank and removed channels are left out, and the image is not smoothed or
contrast-enhanced first.

% source: bin/segment_patch.py:33-45
% source: modules/local/utils.nf:112-131
% source: modules/local/utils.nf:171-201
% source: docs/decisions.md#segmentation

**Inputs and outputs.** In: one patch of the full image, with the selected markers (never the
[projection](projection.md)). Out: polygons in the store, `instanseg_cells` and with nuclei
`instanseg_nuclei`, then a table `instanseg_table` after [quantification](quantification.md). See
[The SpatialData store](../outputs/zarr.md).

% source: modules/local/utils.nf:196-201
% source: docs/output.md#spatialdata-directory

## Similar tools

- **[Cellpose](cellpose.md)** and **Mesmer**
  ([Greenwald et al. 2022](https://doi.org/10.1038/s41587-021-01094-0)) take one or two input
  images, so a multiplex panel must be reduced to a nuclear and a membrane image first.

InstanSeg reads every marker the sheet lists as a nuclear stain or marker, without picking two by
hand. Next to Cellpose it gives a second opinion on the same image: each method gets its own
table, and when both segment cells the QC compares them.

% source: modules/local/utils.nf:196-201
% source: docs/superpowers/specs/2026-11-02-nuclei-cells-design.md

## Read more

- InstanSeg: [@doi:10.48550/arXiv.2408.15954].
- InstanSeg for multiplexed images: [@doi:10.1101/2024.09.04.611150].
- [InstanSeg on GitHub](https://github.com/instanseg/instanseg).
- [Tutorial: exemplar-001](../tutorials/exemplar-001.md).

Version used:

```{include} ../_generated/modules/instanseg.md

```
