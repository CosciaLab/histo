# Cell segmentation: InstanSeg

## The idea

InstanSeg finds nuclei and cells in microscopy images. For every pixel its network predicts a
**seed map**, the distance to the nearest object boundary, and an **embedding**, a short vector
describing where the pixel sits within its object. Seeds are the local maxima of the seed map.
For each seed, a small network compares every nearby pixel's embedding with the seed's and
outputs the probability that the pixel belongs to that object. Seeds that land in the same
object are merged, and each pixel goes to its most probable object [@doi:10.48550/arXiv.2408.15954].

% source: doi:10.48550/arXiv.2408.15954

It was built to be fast and portable: the authors report at least 60 % less processing time than
the most widely used methods, and the models are saved as TorchScript, with GPU support on a range
of hardware [@doi:10.48550/arXiv.2408.15954].

% source: doi:10.48550/arXiv.2408.15954

For multiplexed fluorescence, a channel-invariant front end, ChannelNet, treats the channels as an
unordered set. Each channel passes through the same network, their features are pooled, and the
result is a fixed three-channel image, whatever the number or order of markers. Two decoder
branches then predict nuclei and whole cells. Training images were resized to 0.5 µm per pixel
[@doi:10.1101/2024.09.04.611150].

% source: doi:10.1101/2024.09.04.611150

:::{figure} ../images/how-it-works/instanseg-channelnet-fig1.jpg
:alt: A network diagram in which two marker channels pass through parallel branches joined by max pooling, and two examples showing eight marker channels, their three-channel summary and the resulting nucleus and cell masks.

(a) ChannelNet: each channel passes through the same network, and features are shared across
channels by max pooling, so the number and order of channels do not matter. (b) Two multiplexed
images: eight input channels, the three-channel representation, and the predicted nuclei and
cells. Reproduced from [@doi:10.1101/2024.09.04.611150], CC BY 4.0.
:::

## Why this pipeline uses it

InstanSeg reads every marker the sheet marks as a nuclear stain or marker, not two channels picked
by hand. With Cellpose it gives a second opinion on the same image: each method gets its own table,
and when both segment cells the QC compares them.

% source: modules/local/utils.nf:196-201
% source: docs/superpowers/specs/2026-11-02-nuclei-cells-design.md

## In this pipeline

```{include} ../_generated/modules/instanseg.md

```

- **Model.** sopa's default, `fluorescence_nuclei_and_cells`, unless `instanseg_model_type` names
  another. InstanSeg's README cites the channel-invariant paper for fluorescence nuclei and cells.
- **Channels.** `instanseg_channels`, or from each sample's marker sheet: `dna` and `marker`
  channels for cells, `dna` only for nuclei. Autofluorescence, blank and removed channels are
  left out. InstanSeg reads the full image, never the [projection](projection.md).
- **Pixel size.** `instanseg_pixel_size` tells InstanSeg how to rescale the image to its model's
  resolution.
- **One pass per target.** Through sopa, InstanSeg returns one target at a time, so nuclei and
  cells are two passes over every patch.
- **No CLAHE or smoothing** unless set: sopa's defaults for InstanSeg leave its input as it is.

% source: bin/segment_patch.py:33-45
% source: https://github.com/instanseg/instanseg#readme
% source: modules/local/utils.nf:112-131
% source: modules/local/utils.nf:171-201
% source: subworkflows/local/segmentation/main.nf:41-69
% source: docs/superpowers/specs/2026-11-02-nuclei-cells-design.md
% source: docs/decisions.md#segmentation

What steers it:

- [`use_instanseg`](../reference/parameters.md#use_instanseg),
  [`instanseg_pixel_size`](../reference/parameters.md#instanseg_pixel_size) (required) and
  [`instanseg_channels`](../reference/parameters.md#instanseg_channels).
- [`instanseg_model_type`](../reference/parameters.md#instanseg_model_type) and
  [`instanseg_kwargs`](../reference/parameters.md#instanseg_kwargs).
- [`segment_cells`](../reference/parameters.md#segment_cells) and
  [`segment_nuclei`](../reference/parameters.md#segment_nuclei); see
  [Methods and targets](../reference/usage.md#methods-and-targets).
- [`patch_width_pixel`](../reference/parameters.md#patch_width_pixel), which sets the memory.
- [`use_gpu`](../reference/parameters.md#use_gpu); see
  [GPU segmentation](../reference/usage.md#gpu-segmentation).

% source: nextflow_schema.json:442-473
% source: nextflow_schema.json:388-406
% source: nextflow_schema.json:236-262

## Caveats

- **`instanseg_pixel_size` is required.** Without it InstanSeg does not rescale, and the run can
  succeed with few or no cells; the pipeline stops at startup instead.
- **Memory grows with patch area × channels**; see
  [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel).
- **At most 10 channels on GPU**, checked at startup, until InstanSeg's GPU memory is measured.
- **Pre-stitched input needs `instanseg_channels`**: the default channels come from the marker
  sheet, which such input does not have.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:646-655
% source: docs/usage.md#choosing-patch_width_pixel
% source: ROADMAP.md#known-limitations
% source: CHANGELOG.md:27-28

## Read more

- InstanSeg: [@doi:10.48550/arXiv.2408.15954].
- InstanSeg for multiplexed images: [@doi:10.1101/2024.09.04.611150].
- [InstanSeg on GitHub](https://github.com/instanseg/instanseg).
