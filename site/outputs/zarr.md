# The Zarr store

`{sample}.zarr` holds everything the pipeline learned about a sample: the image, the outlines of
every cell and nucleus, and one table of measurements per method. It is a
[SpatialData](https://spatialdata.scverse.org/en/stable/) object saved as Zarr: a folder, not a
single file. To read it in Python, see
[Open the results in Python](../getting-started/step-by-step.md#open-the-results-in-python).

% source: docs/output.md#spatialdata-directory

## Layout

`{m}` is the method, `cellpose` or `instanseg`; one set per method.

```text
{sample}.zarr/
├── images/
│   ├── <image>            the image, channels named from the marker sheet
│   └── <image>_projected  with keep_projection: the nuclear and cell channels Cellpose saw
├── shapes/
│   ├── image_patches      the patch grid segmentation ran on
│   ├── region_of_interest with use_tissue_segmentation: the tissue outline
│   ├── {m}_cells          cell outlines, with segment_cells
│   ├── {m}_nuclei         nucleus outlines, with segment_nuclei
│   └── {m}_cytoplasm      each cell minus its nucleus, with both targets
└── tables/
    └── {m}_table          one row per cell; per nucleus in a nuclei-only run
```

- A nucleus belongs to the cell that holds at least half of it: `{m}_nuclei` has a
  `linked_cell_id` column, empty when no cell does.
- `{m}_cytoplasm` holds only cells with some cytoplasm left.
- The `<image>` name is the sample's, with `_backsub` after background subtraction.
- With pre-stitched input, channel names are the image's own.

% source: docs/output.md#spatialdata-directory
% source: site/outputs/outputs.md#what-changes-the-outputs

## Cell ids

Cell ids are `{image}_{m}_cells_{n}` (`{image}_{m}_nuclei_{n}` for nuclei). The same id is the
outline's index in `shapes/` and the row name of the table, so outlines and measurements match
up directly. Ids are unique within a store, not across stores.

% source: docs/output.md#spatialdata-directory

## The table

`tables/{m}_table` is an [AnnData](https://anndata.readthedocs.io) table: one row per cell, one
column per marker and statistic.

| Part                    | Holds                                                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `X`                     | marker intensities over the whole cell, e.g. `CD3_mean`. Statistics set by `quantification_statistics` (default mean, median, standard deviation) |
| `var`                   | per column: `marker` and `statistic`. Select columns with these, not by splitting names                                                           |
| `layers['nucleus']`     | the same columns over the cell's nucleus, with cells and nuclei                                                                                   |
| `layers['cytoplasm']`   | the same over its cytoplasm, with cells and nuclei                                                                                                |
| `obs`                   | per cell: `cell_id`, `slide`, `core_id` on a TMA, shape features (below)                                                                          |
| `obsm['spatial']`       | the cell centres, in pixels                                                                                                                       |
| `uns['quantification']` | the statistics used and how the image was read                                                                                                    |
| `uns['segmentation']`   | the settings each segmentation ran with: check here which parameters made the store                                                               |

Shape features, in pixels and px²: `cell_area`, `cell_perimeter`, `cell_circularity`,
`cell_solidity`, `cell_eccentricity`, `cell_major_axis_length`, `cell_minor_axis_length`. With
cells and nuclei also `n_nuclei`, `nucleus_id`, `cytoplasm_area`, the same seven as `nucleus_*`,
and `nc_ratio` (nucleus area over cell area). A nuclei-only run has `nucleus_*` and no `cell_*`.

Areas are in px², not µm²: the store does not carry the pixel size. Convert with the pixel size
in the stitched OME-TIFF; at 0.65 µm per pixel, 1 px² is 0.42 µm².

With `expand_radius_ratio`, `X` is measured over cells grown outwards by that fraction; the
layers, shape features and centres use the original outlines.

% source: docs/output.md#spatialdata-directory
% source: docs/decisions.md#pixel-size
% source: docs/decisions.md#quantification

## NaN and 0

NaN means "not measured"; 0 means "measured, nothing there".

| Cell                   | `layers`                   | `nucleus_area` | `cytoplasm_area` |
| ---------------------- | -------------------------- | -------------- | ---------------- |
| No linked nucleus      | `nucleus`, `cytoplasm` NaN | 0              | NaN              |
| Nuclei fill the cell   | `cytoplasm` NaN            | > 0            | 0                |
| Covers no pixel centre | `X` and both layers NaN    |                |                  |

Without a linked nucleus, the other `nucleus_*` columns and `nc_ratio` are NaN too. Cells are
never dropped.

% source: docs/output.md#spatialdata-directory

## TMA stores

A dearrayed TMA gives one `{slide}_merged.zarr` per slide instead of one store per core, with
`{slide}_merge_manifest.json` listing what was merged. Every element is prefixed with its core,
`{core_id}__{name}`, for example `TMA01_core001__cellpose_table`, and every table has a
`core_id` column.

When you combine tables from several stores or cores, keep `slide` and `core_id`, and make row
names unique, for example with `anndata.concat(..., index_unique="-")`.

% source: docs/output.md#spatialdata-directory
% source: site/outputs/outputs.md#what-changes-the-outputs

## Names the pipeline owns

Shapes and tables named `{cellpose,instanseg}_{cells,nuclei,cytoplasm,table}` belong to the
pipeline: a run replaces those it writes and removes the rest. Do not give your own additions
these names.

% source: docs/output.md#spatialdata-directory

## Why Zarr

- **Chunked.** The image is stored as many small blocks, so a program reads only the part it
  needs. That is what lets the pipeline segment one patch at a time, and a viewer open a
  whole slide without loading it into memory.
- **Multiscale.** The image is kept at several resolutions, so zooming out is fast.
- **Open and shared.** Zarr and OME-NGFF are community standards. The same store opens in Python
  (spatialdata, napari-spatialdata), and its image in other OME-Zarr viewers.
- **One object for everything.** SpatialData keeps the image, outlines and table together, with
  matching ids, instead of a folder of separate files to keep in step.

% source: docs/decisions.md#architecture
% source: https://spatialdata.scverse.org/en/stable/
% source: https://ngff.openmicroscopy.org/0.5/

## Pitfalls

- **The store is changed in place.** Each step writes into the same store, through links into
  the previous step's folder under `work/`. A `-resume` back to earlier parameters reuses those
  steps and does not restore the earlier store. Check `uns['segmentation']`; if it does not match
  your parameters, rerun that sample without `-resume`. See
  [Resume a run](../getting-started/usage-guide.md#resume-a-run).
- **Many small files.** A store is thousands of files. It can fill a file-count quota before a
  size quota, and copying it file by file is slow: pack it first (`tar`), or copy with `rsync`.
- **Do not open a store while a run writes to it.** You may read it half-written.
- **`publish_dir_mode: symlink`** makes `{sample}.zarr` in `--outdir` a link into `work/`. It
  breaks when `work/` is cleaned. The default, `copy`, is safe.
- **Library versions.** Read the store with a spatialdata version that understands Zarr v3 (see
  [Format](#format)). An older one cannot read it.

% source: docs/usage.md#id-resume-and-the-store
% source: CLAUDE.md (sopa modules mutate the Zarr in place, through symlinks)
% source: nextflow.config:97,124
% source: https://www.nextflow.io/docs/latest/reference/process.html#publishdir

## Format

The stores are **Zarr version 3**: each group and array has its metadata in a `zarr.json` file,
where version 2 used `.zgroup` and `.zattrs`. Image metadata, including channel names, sits under
`attributes.ome` in the image's `zarr.json`, the layout of **OME-NGFF 0.5**. The stores are
written by spatialdata as installed with sopa 2.2.9 and 2.3.0 in the pipeline's containers.

- [Zarr v3 specification](https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html)
- [OME-NGFF 0.5](https://ngff.openmicroscopy.org/0.5/)
- [SpatialData documentation](https://spatialdata.scverse.org/en/stable/)

% source: bin/qc_metrics.py:238-247
% source: bin/resolve_segmentation.py:22-28
% source: bin/set_channel_names.py:47-62
% source: containers.tsv (python_sopa sopa=2.2.9; josenimo/sopa sopa==2.3.0)
