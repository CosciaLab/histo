# Data on disk: SpatialData

## The idea

SpatialData is a data format and Python library for spatial omics. A dataset is built from five
kinds of element: **images**, **labels** (segmentation masks), **points**, **shapes** (polygons,
such as cells) and **tables** (one row per cell, with its measurements). Each element carries a
transformation into a shared coordinate system, so elements from different sources can be
overlaid and queried together [@doi:10.1038/s41592-024-02212-x].

% source: doi:10.1038/s41592-024-02212-x

On disk a SpatialData object is a Zarr store, a directory built on OME-NGFF. Zarr stores arrays
in chunks and at several resolutions, so a program loads only the chunks and the resolution it
needs. Data larger than memory can be read lazily, one piece at a time.

% source: doi:10.1038/s41592-024-02212-x

:::{figure} ../images/how-it-works/spatialdata-fig1.png
:alt: Six panels: the five element types stored as OME-NGFF Zarr, the Python library aligning and querying datasets, readers for several technologies, napari annotation, a PyTorch interface and ecosystem tools.

SpatialData's design. (a) The storage format: tables, points, shapes, labels and images in Zarr.
(b) The Python library: aligned datasets, spatial queries and aggregation. (c–f) Readers,
annotation, deep learning and ecosystem tools, which this pipeline does not use. Reproduced from
[@doi:10.1038/s41592-024-02212-x], CC BY 4.0.
:::

## Why this pipeline uses it

The downstream half comes from nf-core/sopa, which is built on SpatialData. Sopa converts any
input into a SpatialData object first, then reads the image lazily, chunk by chunk, so the whole image
never has to fit in memory [@doi:10.1038/s41467-024-48981-z].

% source: docs/decisions.md#architecture
% source: doi:10.1038/s41467-024-48981-z

## In this pipeline

```{include} ../_generated/modules/spatialdata.md

```

- `TO_SPATIALDATA` converts each stitched OME-TIFF into `{sample}.zarr` with `sopa convert`.
- `SET_CHANNEL_NAMES` writes the marker sheet's names onto the image channels. Ashlar and
  Coreograph drop them; without this step channels would be called `Channel:0:0` and so on. Only
  about 5 KB of metadata changes, whatever the image size. Pre-stitched input
  (`use_preprocessing: false`) skips it and keeps its own names.
- Later steps add elements to the same store: the tissue outline, the patch grid, the projection,
  and finally the shapes and one table per method. See
  [output](../reference/output.md#spatialdata-directory) for the final layout.
- Only `WRITE_SEGMENTATIONS` writes shapes and tables. Patch, resolve, link and aggregate tasks
  write files instead, because parallel writers race on the store's root metadata and the last
  one wins silently.
- On a TMA each core has its own store until `MERGE_SPATIALDATA` joins them per slide, one element
  at a time, as `{core_id}__{name}`.
- `PUBLISH_SPATIALDATA` copies the finished store to the results directory.

% source: workflows/histo.nf:30-37
% source: workflows/histo.nf:66-80
% source: modules/local/utils.nf:217-225
% source: docs/decisions.md#channel-names
% source: docs/decisions.md#segmentation
% source: docs/decisions.md#the-tma-path
% source: docs/output.md#spatialdata-directory

What steers it: nothing directly. [`use_preprocessing`](../reference/parameters.md#use_preprocessing)
decides whether channel names come from the marker sheet.

% source: workflows/histo.nf:71-80

## Caveats

- **The store holds no pixel size.** Images stay in pixels, and so do all areas and lengths.
  Storing microns would silently turn `patch_width_pixel` and `min_area_pixels2` into microns.
  The pixel size stays in the stitched OME-TIFF.
- **Steps change the store in place**, through a link into the previous task's work directory.
  `-resume` to earlier parameters does not restore an earlier store; see
  [-resume and the store](../reference/usage.md#id-resume-and-the-store).
- **The OME-TIFF keeps unnamed channels.** Names are written only into the Zarr, since renaming
  in the TIFF would mean copying the whole image.
- **Do not name your own elements** `{cellpose,instanseg}_{cells,nuclei,cytoplasm,table}`: the
  pipeline replaces or removes them.

% source: docs/decisions.md#pixel-size
% source: docs/usage.md#-resume-and-the-store
% source: docs/decisions.md#channel-names
% source: docs/output.md#spatialdata-directory

## Read more

- The SpatialData paper: [@doi:10.1038/s41592-024-02212-x].
- [SpatialData documentation](https://spatialdata.scverse.org/en/stable/).
- The Sopa paper, on how it uses SpatialData: [@doi:10.1038/s41467-024-48981-z].
