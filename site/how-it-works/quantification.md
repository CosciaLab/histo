# Quantification

:::{note}
Statistics beyond the mean and the shape features are new in 3.0.0, not yet released. v2.0.0
measures the mean only and has one `area` column.
:::

% source: CHANGELOG.md:6-23

## The idea

Each cell becomes one row of a table. For every marker, the pipeline takes all the pixels inside
the cell's polygon, holes excluded, and summarises them: by default the mean, the median and the
standard deviation. With nuclei linked to cells, the same is done for the nucleus compartment and
the cytoplasm. Each cell also gets shape features, measured on the polygon itself.

% source: bin/aggregate_compartments.py:1-12
% source: docs/output.md#spatialdata-directory

| Shape feature     | Meaning                                                     |
| ----------------- | ----------------------------------------------------------- |
| area, perimeter   | in px² and px                                               |
| circularity       | 4π × area / perimeter²; 1 for a circle                      |
| solidity          | area / area of the convex hull                              |
| eccentricity      | of the ellipse with the same second moments; 0 for a circle |
| major, minor axis | lengths of that ellipse's axes                              |
| `nc_ratio`        | nucleus area / cell area, with linked nuclei                |

% source: bin/measure_shapes.py:1-8
% source: docs/superpowers/specs/2026-11-05-quantification-design.md

:::{note} Figure pending
One cell over a marker channel with its whole-cell, nucleus and cytoplasm outlines, and its row in
the table, from an exemplar-001 run with both targets.
:::

## Why this pipeline uses it

- **The menu is `mean`, `median`, `std`, `min`, `max`, `q25`, `q75`, `q90`.** No benchmark ranks
  statistics for phenotyping, and the mean is the baseline, so it is required; QC also clusters on
  it. Median and quartiles are the usual extras.
- **`q99` is not offered**: in a 50-pixel cell it is the maximum. `min` is mostly background and
  `max` a hot pixel or a bright neighbour, so both are QC signals, off by default.
- **Morphology is exact.** Features come from the polygon, not a pixel mask. They are a weak but
  independent signal in tissue.
- **Holes count.** sopa's mask drawing ignores holes, so a cytoplasm ring would be measured as the
  whole cell. The pipeline's copy cuts them out.

% source: docs/decisions.md#quantification
% source: docs/decisions.md#segmentation
% source: docs/superpowers/specs/2026-11-05-quantification-design.md

## In this pipeline

```{include} ../_generated/modules/quantification.md

```

- `AGGREGATE` runs once per sample and method and writes `{method}_table` to a file;
  `WRITE_SEGMENTATIONS` puts it into the store.
- **Rows** are cells, or nuclei in a nuclei-only run. `X` holds the whole-cell statistics, named
  `{marker}_{statistic}` (`CD3_mean`); layers `nucleus` and `cytoplasm` hold the compartments.
  Shape features go in `obs`. The full layout is in
  [output](../reference/output.md#spatialdata-directory).
- **Tiles, not patches.** The image is read in 2048 px tiles. A cell belongs to the tile holding
  its centroid, and that tile's window grows to cover it, so every cell is measured whole and the
  tile size does not change the result. Segmentation patches are not reused: they are a resource
  setting, and the table should not depend on one.
- `std` is the population standard deviation; quantiles use numpy's linear interpolation.
- Values are stored as 32-bit floats.

% source: subworkflows/local/segmentation/main.nf:150-180
% source: bin/aggregate_compartments.py:95-177
% source: docs/decisions.md#quantification
% source: docs/output.md#spatialdata-directory
% source: CHANGELOG.md:13

What steers it:

- [`quantification_statistics`](../reference/parameters.md#quantification_statistics), default
  `mean,median,std`: comma-separated, no spaces, must include `mean`.
- [`expand_radius_ratio`](../reference/parameters.md#expand_radius_ratio): grow each cell by this
  ratio times its mean radius before measuring `X`, to catch membrane stains at the edge. The
  layers, shape features and centroids use the unexpanded cell.
- [`segment_nuclei`](../reference/parameters.md#segment_nuclei) with
  [`segment_cells`](../reference/parameters.md#segment_cells): adds the compartment layers.

% source: nextflow_schema.json:302-321
% source: conf/modules.config:80-87

## Caveats

- **Pixel units only.** Areas are px², lengths px; the store has no pixel size. Convert with the
  pixel size in the stitched OME-TIFF.
- **Circularity is NaN below 30 px²**, where it is unstable. It also depends on how the
  method drew the polygon (sopa smooths outlines), so compare it within one method only.
- **NaN means "not measured", 0 "measured, nothing there".** A cell that covers no pixel centre has
  NaN statistics. Cells are never dropped.
- **Quantiles of small cells are coarse**: a 50-pixel cell has only 50 values.

% source: docs/decisions.md#quantification
% source: bin/measure_shapes.py:21
% source: docs/output.md#spatialdata-directory

## Read more

- [The design](https://github.com/CosciaLab/histo/blob/dev/docs/superpowers/specs/2026-11-05-quantification-design.md),
  with the definitions of each feature.
- [Reading the table](../reference/output.md#spatialdata-directory), including how to select one
  statistic.
