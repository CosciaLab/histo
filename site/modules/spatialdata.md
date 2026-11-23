# SpatialData: data on disk

## What it does

After stitching, each image is converted into a SpatialData store: one folder (`{sample}.zarr`)
that holds the image, the cell outlines and the table of measurements together, aligned to each
other.

% source: doi:10.1038/s41592-024-02212-x
% source: workflows/histo.nf:30-37

## Parameters

None directly. [`use_preprocessing`](../inputs/parameters-full.md#use_preprocessing) decides
where channel names come from: the [marker sheet](../inputs/markers.md) when the pipeline
stitched the image, or the image's own names when you give a stitched image.

% source: workflows/histo.nf:71-80
% source: modules/local/utils.nf:217-225

## How it works

SpatialData is a data format and Python library for spatial omics. A dataset is built from five
kinds of element: **images**, **labels** (segmentation masks), **points**, **shapes** (polygons,
such as cells) and **tables** (one row per cell, with its measurements). Each element carries a
transformation into a shared coordinate system, so elements from different sources can be
overlaid and queried together [@doi:10.1038/s41592-024-02212-x].

On disk it is a Zarr store, a folder built on the OME-NGFF image standard. Zarr stores arrays in
chunks and at several resolutions, so a program loads only the chunks and the resolution it needs,
and an image larger than memory can be read one piece at a time.

% source: doi:10.1038/s41592-024-02212-x

:::{figure} ../images/modules/spatialdata-fig1.png
:alt: Six panels: the five element types stored as OME-NGFF Zarr, the Python library aligning and querying datasets, readers for several technologies, napari annotation, a PyTorch interface and ecosystem tools.

SpatialData's design. (a) The storage format: tables, points, shapes, labels and images in Zarr.
(b) The Python library: aligned datasets, spatial queries and aggregation. (c–f) Readers,
annotation, deep learning and ecosystem tools, which this pipeline does not use. Reproduced from
[@doi:10.1038/s41592-024-02212-x], CC BY 4.0.
:::

The store is built up step by step:

1. The stitched OME-TIFF is converted into `{sample}.zarr`.
2. The marker names from the marker sheet are written onto the image's channels. Stitching drops
   them; without this step channels would be called `Channel:0:0` and so on.
3. Later steps add the tissue outline, the patch grid, the [projection](projection.md), and
   finally the cell outlines and one table per segmentation method.
4. On a TMA each core has its own store until the cores are merged into one store per slide,
   with every element renamed `{core_id}__{name}`.
5. The finished store is copied to your results folder.

% source: workflows/histo.nf:30-37
% source: workflows/histo.nf:66-80
% source: docs/decisions.md#channel-names
% source: docs/decisions.md#the-tma-path

Images stay in pixels, and so do all areas and lengths; the pixel size stays in the stitched
OME-TIFF.

% source: docs/decisions.md#pixel-size

**Inputs and outputs.** In: one stitched OME-TIFF per sample (or per TMA core). Out:
`{sample}.zarr` (or `{slide}_merged.zarr` on a TMA) in your results folder. Its layout, and how
to open it: [The SpatialData store](../outputs/zarr.md).

% source: docs/output.md#spatialdata-directory

## Similar tools

- **OME-TIFF images with CSV tables**, as MCMICRO writes them: simple, but outlines, image and
  table sit in separate files that you align yourself.
- **AnnData** alone (`.h5ad`) holds the table but not the image or outlines.

SpatialData came with the downstream half from nf-core/sopa, which is built on it. Sopa reads the
image chunk by chunk, so the whole image never has to fit in memory
[@doi:10.1038/s41467-024-48981-z].

% source: docs/decisions.md#architecture
% source: doi:10.1038/s41467-024-48981-z
% source: doi:10.1038/s41592-021-01308-y

## Read more

- The SpatialData paper: [@doi:10.1038/s41592-024-02212-x].
- [SpatialData documentation](https://spatialdata.scverse.org/en/stable/).
- The Sopa paper, on how it uses SpatialData: [@doi:10.1038/s41467-024-48981-z].

Version used:

```{include} ../_generated/modules/spatialdata.md

```
