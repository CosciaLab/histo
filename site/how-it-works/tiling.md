# Tiled segmentation: sopa

## The idea

Segmentation models need a lot of memory on large images. Sopa therefore cuts the image into
small square patches that overlap, segments each patch on its own, and turns each patch's masks
into polygons. The overlap should be at least twice the average cell diameter, so that every cell
lies whole in at least one patch [@doi:10.1038/s41467-024-48981-z].

% source: doi:10.1038/s41467-024-48981-z

A cell in an overlap is found twice, once by each patch. Sopa resolves such conflicts by area:
when two polygons share at least half the area of the smaller one, they are replaced by their
union. Otherwise both are kept. In the Sopa paper conflicts were rare (0.007 % of Cellpose cell
pairs) and patching did not measurably change segmentation quality.

% source: doi:10.1038/s41467-024-48981-z
% source: https://github.com/prism-oncology/sopa/blob/v2.3.0/sopa/segmentation/resolve.py

:::{figure} ../images/how-it-works/tiling.svg
:alt: Two overlapping patches with cells; one cell in the overlap is outlined by both patches, and after resolving it is a single merged outline.

Two overlapping patches. Each finds the cells inside it; the cell in the overlap is found by
both, and resolving merges the two outlines into one.
:::

## Why this pipeline uses it

Tiling is the core reason for the design: it makes segmentation independent of image size, and
inputs range from 5 to 100 GB. Each patch is its own task, so patches segment in parallel on a
cluster, and a task's memory follows the patch, not the slide.

% source: docs/decisions.md#architecture
% source: docs/decisions.md#parameters

## In this pipeline

```{include} ../_generated/modules/tiling.md

```

- **Tissue (optional).** With `use_tissue_segmentation`, `TISSUE_SEGMENTATION` outlines the
  tissue on one level of the image pyramid. Patches are then clipped to it, and patches with no tissue
  are dropped.
- **Patches.** `MAKE_IMAGE_PATCHES` builds one grid per sample, shared by every method and
  target. It runs after tissue segmentation and projection.
- **Segmentation.** One `SEGMENT_PATCH` task per patch and per method × target; see
  [Cellpose](cellpose.md) and [InstanSeg](instanseg.md).
- **Resolve.** `RESOLVE` collects one segmentation's patches, in patch order, and resolves the
  overlaps with sopa. It then numbers the shapes `{image}_{method}_{target}_{n}`; the fixed order
  gives the same ids on a rerun. It writes a file, not into the store.
- A sample with 0 patches, or a segmentation that resolves to no cells, stops the run and names
  it.

% source: workflows/histo.nf:82-103
% source: https://github.com/prism-oncology/sopa/blob/v2.3.0/sopa/patches/patches.py
% source: subworkflows/local/segmentation/main.nf:34-40
% source: subworkflows/local/segmentation/main.nf:71-105
% source: bin/resolve_segmentation.py:1-80
% source: docs/decisions.md#segmentation

What steers it:

- [`patch_width_pixel`](../reference/parameters.md#patch_width_pixel), default 2000: the patch
  side. Aim for 16 to 200 patches; see
  [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel).
- [`patch_overlap_pixel`](../reference/parameters.md#patch_overlap_pixel), default 100: about
  twice a cell diameter.
- [`use_tissue_segmentation`](../reference/parameters.md#use_tissue_segmentation), with
  [`level`](../reference/parameters.md#level), [`mode`](../reference/parameters.md#mode) and
  [`tissue_segmentation_kwargs`](../reference/parameters.md#tissue_segmentation_kwargs).
- [`min_area_pixels2`](../reference/parameters.md#min_area_pixels2): drops smaller objects in
  each patch. Unset, nothing is dropped.

% source: nextflow_schema.json:236-301
% source: docs/usage.md#choosing-patch_width_pixel
% source: ROADMAP.md#known-limitations

## Caveats

- **`patch_width_pixel` is not set for you.** It changes results at patch boundaries, so an
  automatic value would segment the same slide differently on different hardware. The
  default suits TMA cores and small slides; one patch means no parallelism at all.
- **The default is below sopa's 5000 px** to keep InstanSeg's memory down: its memory grows with
  patch area times channels.
- **An empty patch inside tissue is a failure.** The QC report's "Cells per patch" map shows the
  grid; empty patches at the slide edge are background.
- **A cell wider than the overlap** may lie whole in no patch.
- **Tissue segmentation can find no tissue**, which leaves 0 patches and stops the run.

% source: docs/decisions.md#parameters
% source: docs/usage.md#choosing-patch_width_pixel
% source: bin/qc_report.py:1738-1750
% source: doi:10.1038/s41467-024-48981-z
% source: subworkflows/local/segmentation/main.nf:36-40

## Read more

- The Sopa paper, on patches and conflicts: [@doi:10.1038/s41467-024-48981-z].
- [Sopa documentation](https://prism-oncology.github.io/sopa/).
