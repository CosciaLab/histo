# Cellpose: cell segmentation

## What it does

Cellpose draws an outline around every cell, or every nucleus, in an image. It is a single
deep-learning model, trained on many kinds of images, that works on new images without
retraining.

% source: doi:10.1038/s41592-020-01018-x
% source: doi:10.1101/2025.04.28.651001

## Parameters

- [`use_cellpose`](../inputs/parameters-full.md#use_cellpose): turns Cellpose on.
- Which image it sees, one of:
  - [`cellpose_channels`](../inputs/parameters-full.md#cellpose_channels): one or two marker
    names, nuclear stain last, e.g. `"CD45 DNA_1"`;
  - [`use_projection`](../inputs/parameters-full.md#use_projection): combine many markers into
    one cell image and one nuclear image; see [Channel projection](projection.md).
- [`segment_cells`](../inputs/parameters-full.md#segment_cells) and
  [`segment_nuclei`](../inputs/parameters-full.md#segment_nuclei): cells, nuclei or both.
- [`flow_threshold`](../inputs/parameters-full.md#flow_threshold) and
  [`cellprob_threshold`](../inputs/parameters-full.md#cellprob_threshold). Set them to Cellpose's
  own values, `0.4` and `0`, with [`clip_limit`](../inputs/parameters-full.md#clip_limit) `0`:
  left unset, sopa's values (2, -6 and contrast enhancement 0.2) tile the tissue into cells.
- Before the model: [`clip_limit`](../inputs/parameters-full.md#clip_limit) and
  [`clahe_kernel_size`](../inputs/parameters-full.md#clahe_kernel_size) (contrast enhancement),
  [`gaussian_sigma`](../inputs/parameters-full.md#gaussian_sigma) (smoothing).
- [`pretrained_model`](../inputs/parameters-full.md#pretrained_model) and
  [`cellpose_kwargs`](../inputs/parameters-full.md#cellpose_kwargs) for other Cellpose options.
- [`use_gpu`](../inputs/parameters-full.md#use_gpu): segment on a GPU; see
  [GPU](../inputs/parameters.md#gpu).

More in [Methods and targets](../inputs/parameters.md#methods-and-targets) and
[Many markers with Cellpose](../inputs/parameters.md#many-markers-with-cellpose).

% source: nextflow_schema.json:322-342
% source: nextflow_schema.json:388-441
% source: nextflow_schema.json:236-262
% source: modules/local/utils.nf:83-111
% source: docs/decisions.md#channel-projection

## How it works

For every pixel the network predicts the probability of being inside a cell, and two flow maps,
horizontal and vertical, that point towards the cell's centre. Following the flows from every
pixel groups the pixels into cells, one mask each [@doi:10.1038/s41592-020-01018-x].

% source: doi:10.1038/s41592-020-01018-x

This pipeline runs **Cellpose-SAM**, which keeps that output but replaces the network with the
image encoder of SAM, a large general-purpose segmentation model. It was trained to ignore channel
order and to cope with cell diameters from 7.5 to 120 px, so it needs no diameter estimate, with
a small loss of accuracy on very small cells [@doi:10.1101/2025.04.28.651001]. The model is
built into the container, so nothing is downloaded during a run.

% source: doi:10.1101/2025.04.28.651001
% source: modules/local/segment_patch/main.nf:6-24
% source: docs/decisions.md#parameters

:::{note} Figure pending
Cellpose outlines on one crop at full resolution, from the "Segmentation overlay" section of an
exemplar-001 QC report.
:::

Cellpose runs on every [patch](tiling.md) separately; the patches are then joined. If it
segmented both cells and nuclei, they are [linked](linking.md). Cellpose-SAM is slow without a
GPU: about 24 s per 1200 px crop on an Apple GPU.

% source: docs/decisions.md#channel-projection
% source: subworkflows/local/segmentation/main.nf:71-105

**Inputs and outputs.** In: one patch of the image, as one or two channels: a cell channel and a
nuclear channel for cells, the nuclear channel alone for nuclei. Out: polygons in the store,
`cellpose_cells` and with nuclei `cellpose_nuclei`, then a table `cellpose_table` after
[quantification](quantification.md). See [The SpatialData store](../outputs/zarr.md).

% source: bin/segment_patch.py:23-45
% source: docs/output.md#spatialdata-directory

## Similar tools

- **StarDist** fits star-shaped outlines, which suits round nuclei
  ([@doi:10.1007/978-3-030-00934-2_30]). This pipeline used it for nuclei until version 2.0.
- **Mesmer** segments cells from one nuclear and one membrane image, trained on tissue
  ([Greenwald et al. 2022](https://doi.org/10.1038/s41587-021-01094-0)).
- **[InstanSeg](instanseg.md)**, the pipeline's other method, reads every marker at once.

Cellpose is a widely used generalist model. Cellpose-SAM replaced Cellpose 3 (`cyto3`): in the
projection benchmark Cyto3 fell back to nuclei where Cellpose-SAM found whole cells, at about
eight times the run time. StarDist was dropped in 2.0, since Cellpose and InstanSeg also segment
nuclei.

% source: docs/decisions.md#parameters
% source: docs/decisions.md#segmentation
% source: doi:10.1007/978-3-030-00934-2_30

## Read more

- Cellpose: [@doi:10.1038/s41592-020-01018-x].
- Cellpose-SAM: [@doi:10.1101/2025.04.28.651001].
- [Cellpose documentation](https://cellpose.readthedocs.io/).
- [Tutorial: multiple segmentations](../tutorials/multiple-segmentations.md).

Version used:

```{include} ../_generated/modules/cellpose.md

```
