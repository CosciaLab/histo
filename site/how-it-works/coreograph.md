# TMA dearray: Coreograph

## The idea

A tissue microarray (TMA) carries many small tissue cores, 0.3 to 2 mm across, on one slide.
Coreograph splits the stitched slide image into one multichannel image per core, so each core
can be processed on its own [@doi:10.1038/s41592-021-01308-y].

% source: doi:10.1038/s41592-021-01308-y

It uses a UNet, a deep-learning network trained on two classes, core tissue and background. The
network turns the nuclear channel into a probability map that accentuates the cores, which helps
find cores that are dim or fragmented. Cores are then cropped from the stitched image based on
their median diameter. When cores touch, a Laplacian of Gaussian filter sized from that median
diameter separates them.

% source: doi:10.1038/s41592-021-01308-y

The network runs on a downsampled copy of the image; MCMICRO's default factor of 5 matches the
training data. `--buffer` adds space around each core before cropping. Besides the cores,
Coreograph writes a mask per core, a labelled map of the whole array and the core centroids, for
checking what it found.

% source: https://mcmicro.org/parameters/core.html#coreograph

:::{note} Figure pending
Sweep overlays: detected cores at downsample factors 3 to 7 side by side, from
`preprocessing/dearray/sweep/{slide}_sweep_overlays.png` of an exemplar TMA run.
:::

## Why this pipeline uses it

TMA dearray comes from nf-core/mcmicro, with the preprocessing half. Each core then runs the
whole downstream half alone and is merged back per slide at the very end: many small, dense
images segment better than one large, sparse one, and per-core QC survives.

% source: docs/decisions.md#architecture
% source: docs/decisions.md#the-tma-path

Coreograph finds cores reliably only at the right downsample factor, and a wrong one fails
silently. So unless told otherwise, the pipeline tries several factors and keeps the best; see
[TMA dearray](../reference/usage.md#tma-dearray).

% source: docs/usage.md#tma-dearray

## In this pipeline

```{include} ../_generated/modules/coreograph.md

```

- Runs once per slide, after Ashlar and before background subtraction, so each core keeps an
  unsubtracted image for QC.
- **The sweep.** `COREOGRAPH_DETECT` runs the UNet and core detection at factors 3, 4, 5, 6 and
  7, without writing core images. `COREOGRAPH_SELECT` scores each factor as count error plus
  diameter error plus spread of core sizes; the lowest wins, ties going to the smaller factor.
  It warns when even the best factor is off by more than 10 % in count or 25 % in diameter, and
  stops when no factor found any core.
- `COREOGRAPH` then dearrays once with the chosen factor, on the marker sheet's first `dna`
  channel, with `--buffer 2 --sensitivity 0.3`.
- Diameters are compared in mm using the pixel size from the image's OME-XML; without it the
  sweep stops and asks for `coreograph_args`.
- Cores are named `{slide}_core001` and so on. Each continues as its own sample, with its
  slide's marker sheet. Outputs are under `preprocessing/dearray/`; see
  [output](../reference/output.md#preprocessing).

% source: subworkflows/local/preprocess_images/main.nf:54-104
% source: conf/modules.config:49-78
% source: bin/coreograph_select.py:1-80
% source: bin/coreograph_detect.py:1-8
% source: bin/coreograph_detect.py:45-60
% source: CHANGELOG.md:367-368

What steers it:

- [`use_tma_dearray`](../reference/parameters.md#use_tma_dearray): turns the step on. Needs
  [`use_preprocessing`](../reference/parameters.md#use_preprocessing).
- [`tma_expected_cores`](../reference/parameters.md#tma_expected_cores) and
  [`tma_core_diameter_mm`](../reference/parameters.md#tma_core_diameter_mm): what the sweep
  scores against.
- [`coreograph_args`](../reference/parameters.md#coreograph_args): run Coreograph exactly as
  given; the sweep is skipped.
- [`skip_reference_dna_check`](../reference/parameters.md#skip_reference_dna_check): run even
  when the dearray channel is not `dna`.

% source: nextflow_schema.json (preprocessing group)

## Caveats

- **A wrong factor fails silently**: cores split along tissue bands, or neighbours merge. Look
  at the sweep overlays and the TMA map even when the run succeeds.
- **One layout per run.** Every slide is scored against the same expected count and diameter;
  run arrays with different layouts separately.
- **The dearray channel must be `dna`**, or the run stops at startup.
- **No Mac runs.** Coreograph fails under Rosetta (no AVX); see
  [On the Mac](https://github.com/CosciaLab/histo/blob/dev/docs/CONTRIBUTING.md#on-the-mac).

% source: docs/usage.md#tma-dearray
% source: docs/usage.md#inputs
% source: docs/output.md#preprocessing
% source: docs/CONTRIBUTING.md#on-the-mac

## Read more

- MCMICRO, where Coreograph is described: [@doi:10.1038/s41592-021-01308-y].
- [Coreograph parameters](https://mcmicro.org/parameters/core.html#coreograph) and
  [source](https://github.com/HMS-IDAC/UNetCoreograph).
