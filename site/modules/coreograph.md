# Coreograph: TMA dearray

## What it does

A tissue microarray (TMA) carries many small tissue cores on one slide. Coreograph finds the cores
in the stitched slide image and cuts out one image per core, so each core is segmented and checked
on its own.

% source: doi:10.1038/s41592-021-01308-y
% source: docs/decisions.md#the-tma-path

## Parameters

- [`use_tma_dearray`](../inputs/parameters-full.md#use_tma_dearray): turns the step on. Needs
  [`use_preprocessing`](../inputs/parameters-full.md#use_preprocessing).
- [`tma_expected_cores`](../inputs/parameters-full.md#tma_expected_cores): how many cores are on
  the slide (a count, not rows × columns).
- [`tma_core_diameter_mm`](../inputs/parameters-full.md#tma_core_diameter_mm): the core diameter in
  mm. With the count, it decides which detection setting is kept (see below). Both apply to every
  slide in the run, so run arrays with different layouts separately.
- [`coreograph_args`](../inputs/parameters-full.md#coreograph_args): run Coreograph exactly with
  these options instead; the automatic choice is skipped.
- [`skip_reference_dna_check`](../inputs/parameters-full.md#skip_reference_dna_check): with
  `coreograph_args`, run even when its `--channel` is not a nuclear stain.

More in [TMA dearray](../inputs/parameters.md#tma-dearray).

% source: nextflow_schema.json:47-52
% source: nextflow_schema.json:84-118
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:476-488
% source: docs/usage.md#tma-dearray

## How it works

Coreograph uses a UNet, a deep-learning network trained on two classes, core tissue and
background. The network turns the nuclear stain into a probability map that accentuates the
cores, which helps find cores that are dim or fragmented. Cores are then cropped from the
stitched image based on their median diameter. When cores touch, a filter sized from that median
diameter separates them [@doi:10.1038/s41592-021-01308-y].

% source: doi:10.1038/s41592-021-01308-y

The network runs on a downsampled copy of the image, and finds cores reliably only at the right
downsample factor. A wrong one fails silently: cores split along tissue bands, or neighbours
merge. So the pipeline tries factors 3 to 7 and scores each against your expected count and
diameter (count error plus diameter error plus spread of core sizes). The lowest score wins; ties
go to the smaller factor. The log warns when even the best factor is off by more than 10 % in
count or 25 % in diameter, and the run stops when no factor found any core. Coreograph then cuts
the cores once, with the chosen factor, on the marker sheet's first `dna` channel.

% source: https://mcmicro.org/parameters/core.html#coreograph
% source: subworkflows/local/preprocess_images/main.nf:54-104
% source: bin/coreograph_select.py:1-80
% source: conf/modules.config:49-78

Diameters are compared in mm, using the pixel size in the image's metadata; without it the run
stops and asks for `coreograph_args`.

% source: bin/coreograph_detect.py:45-60

:::{note} Figure pending
Sweep overlays: detected cores at downsample factors 3 to 7 side by side, from
`preprocessing/dearray/sweep/{slide}_sweep_overlays.png` of an exemplar TMA run.
:::

**Inputs and outputs.** In: the stitched slide, one OME-TIFF from [Ashlar](ashlar.md). Out, under
`preprocessing/dearray/`: one OME-TIFF per core, `{slide}_core001.ome.tif` and so on; a mask per
core; a labelled map of the whole array (`{slide}_tma_map.tif`); the core centres; and, in
`sweep/`, the scores and an overlay per factor. Each core then continues through the pipeline as
its own sample, and the cores are merged back into one store per slide at the end. See
[Preprocessing outputs](../outputs/preprocessing.md).

% source: docs/output.md#preprocessing
% source: CHANGELOG.md:367-368
% source: docs/decisions.md#the-tma-path

## Similar tools

- **QuPath's TMA dearrayer** fits a grid of cores, which you check and adjust in QuPath
  ([Bankhead et al. 2017](https://doi.org/10.1038/s41598-017-17204-5)).

Coreograph came with the preprocessing half from nf-core/mcmicro and needs no hand work. The
automatic choice of downsample factor is this pipeline's addition, because a wrong factor fails
silently.

% source: docs/decisions.md#architecture
% source: docs/usage.md#tma-dearray

## Read more

- MCMICRO, where Coreograph is described: [@doi:10.1038/s41592-021-01308-y].
- [Coreograph parameters](https://mcmicro.org/parameters/core.html#coreograph) and
  [source](https://github.com/HMS-IDAC/UNetCoreograph).
- [Tutorial: a TMA](../tutorials/tma.md).

Version used:

```{include} ../_generated/modules/coreograph.md

```
