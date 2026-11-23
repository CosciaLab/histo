# Quantification

## What it does

Each cell becomes one row of a table: for every marker, the intensity of the pixels inside the
cell (mean, median and standard deviation by default), plus the cell's size and shape.

% source: bin/aggregate_compartments.py:1-12
% source: docs/output.md#spatialdata-directory

## Parameters

- [`quantification_statistics`](../inputs/parameters-full.md#quantification_statistics), default
  `mean,median,std`: which summaries to compute. Choose from `mean`, `median`, `std`, `min`,
  `max`, `q25`, `q75`, `q90`; comma-separated, no spaces, and `mean` is always needed.
- [`expand_radius_ratio`](../inputs/parameters-full.md#expand_radius_ratio): grow each cell by
  this ratio times its mean radius before measuring, to catch membrane stains at the edge. Shape
  and compartments use the unexpanded cell.
- [`segment_nuclei`](../inputs/parameters-full.md#segment_nuclei) with
  [`segment_cells`](../inputs/parameters-full.md#segment_cells): also measure the nucleus and the
  cytoplasm of each cell.

% source: nextflow_schema.json:302-321
% source: conf/modules.config:80-87

## How it works

For every marker, all the pixels inside the cell's outline, holes excluded, are summarised. With
nuclei [linked](linking.md) to cells, the same is done for the nucleus compartment and the
cytoplasm. The image is read in 2048 px tiles; a cell belongs to the tile holding its centre, and
that tile grows to cover it, so every cell is measured whole. The segmentation patches are not
reused, so the patch size never changes the table.

% source: bin/aggregate_compartments.py:95-177
% source: docs/decisions.md#quantification

Shape features are measured on the outline itself, not on pixels:

| Shape feature     | Meaning                                                     |
| ----------------- | ----------------------------------------------------------- |
| area, perimeter   | in px² and px                                               |
| circularity       | 4π × area / perimeter²; 1 for a circle; empty below 30 px²  |
| solidity          | area / area of the convex hull                              |
| eccentricity      | of the ellipse with the same second moments; 0 for a circle |
| major, minor axis | lengths of that ellipse's axes                              |
| `nc_ratio`        | nucleus area / cell area, with linked nuclei                |

% source: bin/measure_shapes.py:1-21
% source: docs/superpowers/specs/2026-11-05-quantification-design.md

Areas and lengths are in pixels; convert with the pixel size in the stitched OME-TIFF. An empty
value (NaN) means "not measured", 0 means "measured, nothing there". Cells are never dropped.

% source: docs/decisions.md#quantification
% source: docs/output.md#spatialdata-directory

:::{note} Figure pending
One cell over a marker channel with its whole-cell, nucleus and cytoplasm outlines, and its row in
the table, from an exemplar-001 run with both targets.
:::

**Inputs and outputs.** In: the full image and one method's cell outlines (and nuclei and
cytoplasm, when linked). Out: one table per method, `{m}_table`, in the store. Columns are named
`{marker}_{statistic}`, e.g. `CD3_mean`; the nucleus and cytoplasm values sit in two extra
layers, `nucleus` and `cytoplasm`; shape features are per-cell annotations. Values are 32-bit
floats. See [The SpatialData store](../outputs/zarr.md).

% source: subworkflows/local/segmentation/main.nf:150-180
% source: docs/output.md#spatialdata-directory
% source: CHANGELOG.md:13

## Similar tools

- **MCMICRO's MCQuant** measures mean intensity per cell from a label mask and writes CSV
  ([Schapiro et al. 2022](https://doi.org/10.1038/s41592-021-01308-y)).
- **sopa's own aggregation**, which this step is copied from.

This step is sopa's, with one fix: sopa's mask drawing ignores holes, so a cytoplasm ring would
be measured as the whole cell. Here holes are cut out. Mean is the baseline, since no benchmark
ranks statistics for phenotyping; median and quartiles are the usual extras. `q99` is not
offered: in a 50-pixel cell it is the maximum. `min` and `max` are mostly background and hot
pixels, so they are off by default.

% source: docs/decisions.md#segmentation
% source: docs/decisions.md#quantification
% source: doi:10.1038/s41592-021-01308-y

## Read more

- [The design](https://github.com/CosciaLab/histo/blob/dev/docs/superpowers/specs/2026-11-05-quantification-design.md),
  with the definitions of each feature.
- [Reading the table](../outputs/zarr.md), including how to select one statistic.

Version used:

```{include} ../_generated/modules/quantification.md

```
