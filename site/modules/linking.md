# Linking nuclei and cells

## What it does

When a method segments both nuclei and whole cells, linking decides which nucleus belongs to which
cell, and from that draws each cell's cytoplasm: the cell minus its nucleus.

% source: bin/link_compartments.py:1-10

## Parameters

[`segment_cells`](../inputs/parameters-full.md#segment_cells) and
[`segment_nuclei`](../inputs/parameters-full.md#segment_nuclei), both on: linking then runs for
each method. Nothing else changes it; the one-half rule below is fixed. See
[Methods and targets](../inputs/parameters.md#methods-and-targets).

% source: nextflow_schema.json:388-406
% source: docs/decisions.md#segmentation

## How it works

Nuclei and cells are segmented in two separate passes, so they share nothing but their outlines.
Linking pairs them by overlap, after the patches are [joined](tiling.md), when the outlines are
final:

1. A nucleus links to the cell that holds the largest share of its area, if that share is at
   least half. A tie goes to the cell listed first.
2. A cell's **nucleus compartment** is the union of its linked nuclei, clipped to the cell.
3. Its **cytoplasm** is the cell minus that compartment. It can be a ring, or several pieces.
4. Nothing is dropped: an unlinked nucleus is kept, and a cell without a nucleus is kept.

% source: bin/link_compartments.py:82-160
% source: docs/decisions.md#segmentation

:::{figure} ../images/modules/linking.svg
:alt: Left, a cell with a nucleus inside it; the cell area around the nucleus is the cytoplasm. Right, a cell with a nucleus mostly outside it; the nucleus is not linked, the cell has no nucleus and no cytoplasm is defined.

Left: the nucleus lies inside the cell, so it is linked, and the rest of the cell is cytoplasm.
Right: less than half of the nucleus lies inside, so it is not linked; the cell has no nucleus,
so no cytoplasm is defined.
:::

A cell without a nucleus has no cytoplasm value ("not measured", NaN); a cell its nuclei fill has
a cytoplasm area of 0 ("measured, nothing there").

% source: docs/decisions.md#segmentation

**Inputs and outputs.** In: one method's resolved cells and nuclei. Out, in the store:
`{m}_nuclei` with a `linked_cell_id` per nucleus, and `{m}_cytoplasm`; per cell, the number of
nuclei, the largest linked nucleus and the nucleus and cytoplasm areas. [Quantification](quantification.md)
measures the nucleus compartment and the cytoplasm as extra table layers. The QC report counts
cells by number of nuclei, unlinked nuclei, and cells their nuclei fill. See
[The SpatialData store](../outputs/zarr.md).

% source: subworkflows/local/segmentation/main.nf:120-148
% source: bin/link_compartments.py:163-170
% source: docs/output.md#spatialdata-directory
% source: bin/qc_metrics.py:200-211

## Similar tools

- **Expanding nuclei** by a fixed distance to approximate cells, as QuPath's cell detection does
  ([Bankhead et al. 2017](https://doi.org/10.1038/s41598-017-17204-5)): one segmentation, but the
  cell shape is guessed, not seen.
- **Models that return nuclei and cells together**, matched by construction.

Here each method segments cells from the membrane markers, so linking by geometry is what lets
one run measure nuclei, cells and cytoplasm from the same outlines.

% source: docs/superpowers/specs/2026-11-02-nuclei-cells-design.md
% source: docs/decisions.md#segmentation

## Read more

- [The design](https://github.com/CosciaLab/histo/blob/dev/docs/superpowers/specs/2026-11-02-nuclei-cells-design.md),
  with the linking rules.
- [Shapely](https://shapely.readthedocs.io/), which does the geometry.
- [Tutorial: multiple segmentations](../tutorials/multiple-segmentations.md).

Version used:

```{include} ../_generated/modules/linking.md

```
