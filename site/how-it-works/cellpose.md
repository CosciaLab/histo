# Cell segmentation: Cellpose

## The idea

Cellpose is a generalist cell segmentation model: one network, trained on many kinds of images,
that works on new images without retraining [@doi:10.1038/s41592-020-01018-x]. For every pixel it
predicts the probability of being inside a cell, and two flow maps, horizontal and vertical, that
point towards the cell's centre. Following the flows from every pixel groups the pixels into
cells, one mask each.

% source: doi:10.1038/s41592-020-01018-x
% source: doi:10.1101/2025.04.28.651001

Cellpose-SAM keeps this output but replaces the network with the image encoder of SAM, a large
general-purpose segmentation model. It was trained to ignore channel order and to cope with cell
diameters from 7.5 to 120 px, so it needs no diameter estimate, with a small loss of accuracy on
very small cells. It takes three input channels [@doi:10.1101/2025.04.28.651001].

% source: doi:10.1101/2025.04.28.651001

:::{note} Figure pending
Cellpose outlines on one crop at full resolution, from the "Segmentation overlay" section of an
exemplar-001 QC report.
:::

## Why this pipeline uses it

Cellpose-SAM replaced Cellpose 3 (`cyto3`). In the projection benchmark Cyto3 fell back to
nuclei where Cellpose-SAM found whole cells, at about eight times the run time. The diameter is
fixed at 30 px, Cellpose-SAM's training size, so images are not rescaled.

% source: docs/decisions.md#parameters
% source: docs/decisions.md#channel-projection

## In this pipeline

```{include} ../_generated/modules/cellpose.md

```

- **Model.** `cpsam`, the only weights in the image; they are baked in, so nothing is downloaded
  at run time.
- **Channels.** For cells: `cellpose_channels`, nuclear last, or with `use_projection` the
  projection's `cell` and `nuclear` channels. For nuclei: the nuclear channel alone.
- **Settings left unset take sopa's defaults:** `flow_threshold` 2, `cellprob_threshold` -6,
  CLAHE with `clip_limit` 0.2 and Gaussian smoothing with `gaussian_sigma` 1 before the model.
- One `SEGMENT_PATCH_CELLPOSE` task per patch and target, then [resolve](tiling.md). Cellpose's
  cells and nuclei are linked if both targets ran; see [Linking](linking.md).
- With `use_gpu`, each task gets one GPU and fails if CUDA is not usable, instead of falling back
  to CPU silently.

% source: docs/superpowers/specs/2026-10-29-cellpose-sam-design.md
% source: ROADMAP.md#33-segmentation-defaults
% source: modules/local/segment_patch/main.nf:6-24
% source: modules/local/utils.nf:83-111
% source: bin/segment_patch.py:23-45
% source: docs/decisions.md#parameters

What steers it:

- [`use_cellpose`](../reference/parameters.md#use_cellpose),
  [`cellpose_channels`](../reference/parameters.md#cellpose_channels) or
  [`use_projection`](../reference/parameters.md#use_projection).
- [`segment_cells`](../reference/parameters.md#segment_cells) and
  [`segment_nuclei`](../reference/parameters.md#segment_nuclei); see
  [Methods and targets](../reference/usage.md#methods-and-targets).
- [`flow_threshold`](../reference/parameters.md#flow_threshold),
  [`cellprob_threshold`](../reference/parameters.md#cellprob_threshold),
  [`pretrained_model`](../reference/parameters.md#pretrained_model) and
  [`cellpose_kwargs`](../reference/parameters.md#cellpose_kwargs).
- Before the model: [`clip_limit`](../reference/parameters.md#clip_limit),
  [`clahe_kernel_size`](../reference/parameters.md#clahe_kernel_size) and
  [`gaussian_sigma`](../reference/parameters.md#gaussian_sigma).
- [`use_gpu`](../reference/parameters.md#use_gpu); see
  [GPU segmentation](../reference/usage.md#gpu-segmentation).

% source: nextflow_schema.json:322-342
% source: nextflow_schema.json:388-441
% source: nextflow_schema.json:236-262

## Caveats

- **sopa's thresholds tile the tissue into cells**; Cellpose's own follow the membranes. They are
  documented, not defaulted, so runs without projection do not change; see
  [Two-channel segmentation](../reference/usage.md#two-channel-segmentation-use-projection).
- **Slow without a GPU.** Cellpose-SAM took about 24 s per 1200 px crop on an Apple GPU, against
  3 s for Cyto3.
- **Two channels.** Membrane and cytoplasm markers share the `cell` channel; the Cellpose docs say
  a third channel needs retraining.
- **`cpsam_v2` is not used.** Cellpose 4.2.1.1 defaults to it, but sopa passes `cpsam`, the only
  weights in the image.
- **A `cellpose_kwargs` key that a parameter already sets** (e.g. `diameter`, `channels`) fails
  the patch task, naming it.

% source: docs/decisions.md#channel-projection
% source: docs/usage.md#two-channel-segmentation-use_projection
% source: ROADMAP.md#33-segmentation-defaults
% source: bin/segment_patch.py:93-109
% source: CHANGELOG.md:77-78

## Read more

- Cellpose: [@doi:10.1038/s41592-020-01018-x].
- Cellpose-SAM: [@doi:10.1101/2025.04.28.651001].
- [Cellpose documentation](https://cellpose.readthedocs.io/).
