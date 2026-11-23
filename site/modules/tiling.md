# Sopa: tiled segmentation

## What it does

Sopa cuts the image into overlapping square patches, segments each patch separately, and then
joins the results, merging cells found twice where patches overlap. This lets any image size be
segmented, many patches at a time.

% source: doi:10.1038/s41467-024-48981-z
% source: docs/decisions.md#architecture

## Parameters

- [`patch_width_pixel`](../inputs/parameters-full.md#patch_width_pixel), default 2000: the side
  of a patch in pixels. Aim for 16 to 200 patches; see [Patch size](../inputs/parameters.md#patch-size).
  Keep it the same when you compare runs, since it changes results at patch borders.
- [`patch_overlap_pixel`](../inputs/parameters-full.md#patch_overlap_pixel), default 100: about
  twice a cell diameter.
- [`use_tissue_segmentation`](../inputs/parameters-full.md#use_tissue_segmentation), with
  [`level`](../inputs/parameters-full.md#level), [`mode`](../inputs/parameters-full.md#mode) and
  [`tissue_segmentation_kwargs`](../inputs/parameters-full.md#tissue_segmentation_kwargs): skip
  patches on empty glass; see [Skip empty glass](../inputs/parameters.md#skip-empty-glass).
- [`min_area_pixels2`](../inputs/parameters-full.md#min_area_pixels2): drop objects smaller than
  this, in px². Unset, nothing is dropped.

% source: nextflow_schema.json:236-301
% source: docs/usage.md#choosing-patch-width-pixel
% source: docs/decisions.md#parameters

## How it works

Segmentation models need a lot of memory on large images. Sopa therefore segments small patches
that overlap, and turns each patch's masks into polygons. The overlap should be at least twice the
average cell diameter, so that every cell lies whole in at least one patch
[@doi:10.1038/s41467-024-48981-z].

A cell in an overlap is found twice, once by each patch. When two outlines share at least half the
area of the smaller one, they are replaced by their union; otherwise both are kept. In the Sopa
paper such conflicts were rare (0.007 % of Cellpose cell pairs) and patching did not measurably
change segmentation quality.

% source: doi:10.1038/s41467-024-48981-z
% source: https://github.com/prism-oncology/sopa/blob/v2.3.0/sopa/segmentation/resolve.py

:::{figure} ../images/modules/tiling.svg
:alt: Two overlapping patches with cells; one cell in the overlap is outlined by both patches, and after resolving it is a single merged outline.

Two overlapping patches. Each finds the cells inside it; the cell in the overlap is found by
both, and resolving merges the two outlines into one.
:::

In this pipeline, in order:

1. **Tissue (optional).** With `use_tissue_segmentation`, the tissue is outlined on a coarse
   level of the image: the brightest channel at each pixel (or the one you name) is thresholded
   with Otsu's method. Patches are clipped to the outline, and patches without tissue are dropped.
2. **Patches.** One grid per sample, shared by every method and target.
3. **Segmentation.** Each patch is segmented by [Cellpose](cellpose.md) or
   [InstanSeg](instanseg.md), for cells, nuclei or both, each patch as its own cluster job.
4. **Joining.** The patches of one segmentation are joined in a fixed order, overlaps resolved,
   and the cells numbered, so a rerun gives the same ids.

A sample with no patches, or a segmentation that finds no cells, stops the run and names it.

% source: workflows/histo.nf:82-103
% source: https://github.com/prism-oncology/sopa/blob/v2.2.9/sopa/segmentation/_tissue.py#L148
% source: subworkflows/local/segmentation/main.nf:34-40
% source: subworkflows/local/segmentation/main.nf:71-105
% source: bin/resolve_segmentation.py:1-80
% source: docs/decisions.md#segmentation

**Inputs and outputs.** In: the image in the [SpatialData store](spatialdata.md). Out: the patch
grid (`image_patches`), the tissue outline (`region_of_interest`) when used, and one set of
cell polygons per method and target, all in the store. The QC report's "Cells per patch" map
shows the grid; see [Reports](../outputs/reports.md).

% source: docs/output.md#spatialdata-directory
% source: bin/qc_report.py:1738-1750

## Similar tools

- **Segmenting the whole image at once**, as most pipelines do: simpler, but memory grows with
  the slide, and a 100 GB whole-slide image does not fit.
- **Cellpose's own tiling** splits the image into tiles too, but inside one program on one
  machine.

Tiling is the core reason for this pipeline's design. Inputs range from 5 to 100 GB; with tiling,
the memory a job needs follows the patch, not the slide, and patches run in parallel on a
cluster.

% source: docs/decisions.md#architecture
% source: docs/decisions.md#parameters
% source: https://cellpose.readthedocs.io/en/latest/settings.html (tile)

## Read more

- The Sopa paper, on patches and conflicts: [@doi:10.1038/s41467-024-48981-z].
- [Sopa documentation](https://prism-oncology.github.io/sopa/).

Version used:

```{include} ../_generated/modules/tiling.md

```
