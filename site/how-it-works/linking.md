# Linking nuclei and cells

## The idea

A method segments nuclei and whole cells in two separate passes, so the two sets of shapes share
nothing but their geometry. Linking pairs them by overlap:

1. A nucleus links to the cell that holds the largest share of its area, if that share is at
   least half. A tie goes to the cell listed first.
2. A cell's **nucleus compartment** is the union of its linked nuclei, clipped to the cell.
3. Its **cytoplasm** is the cell minus that compartment. It can be a ring, or several pieces.
4. Nothing is dropped: an unlinked nucleus is kept, and a cell without a nucleus is kept.

% source: bin/link_compartments.py:1-10
% source: bin/link_compartments.py:82-160
% source: docs/decisions.md#segmentation

:::{figure} ../images/how-it-works/linking.svg
:alt: Left, a cell with a nucleus inside it; the cell area around the nucleus is the cytoplasm. Right, a cell with a nucleus mostly outside it; the nucleus is not linked and the cell has no cytoplasm.

Left: the nucleus lies inside the cell, so it is linked, and the rest of the cell is cytoplasm.
Right: less than half of the nucleus lies inside, so it is not linked; the cell has no nucleus
compartment and no cytoplasm.
:::

## Why this pipeline uses it

One run segments nuclei and whole cells, derives the cytoplasm, and measures all three
compartments. Linking happens after [resolve](tiling.md), because only resolved shapes are final. The
0.5 share is a constant, not a parameter.

% source: docs/superpowers/specs/2026-11-02-nuclei-cells-design.md
% source: docs/decisions.md#segmentation

## In this pipeline

```{include} ../_generated/modules/linking.md

```

- `LINK_COMPARTMENTS` runs once per sample and method, when that method segmented both targets.
- It writes four files: the nuclei with `linked_cell_id` (null if unlinked), the nucleus
  compartment, the cytoplasm, and one row per cell with `n_nuclei`, `nucleus_id` (the largest
  linked nucleus), `nucleus_area` and `cytoplasm_area`.
- The nuclei and cytoplasm become shapes `{m}_nuclei` and `{m}_cytoplasm`. The nucleus
  compartment is measured, not stored; [quantification](quantification.md) turns it and the
  cytoplasm into table layers.
- Invalid polygons are repaired with `make_valid` for linking only, and counted in the log. The
  stored shapes are what the method produced.
- The QC report counts cells by number of nuclei (0, 1, 2+), unlinked nuclei, and cells without
  cytoplasm.

% source: subworkflows/local/segmentation/main.nf:120-148
% source: bin/link_compartments.py:61-79
% source: bin/link_compartments.py:163-170
% source: docs/decisions.md#segmentation
% source: docs/output.md#spatialdata-directory
% source: bin/qc_metrics.py:200-211

What steers it:

- [`segment_cells`](../reference/parameters.md#segment_cells) and
  [`segment_nuclei`](../reference/parameters.md#segment_nuclei), both on, for each method you
  enable; see [Methods and targets](../reference/usage.md#methods-and-targets).

% source: nextflow_schema.json:388-406

## Caveats

- **NaN means "not measured", 0 "measured, nothing there".** A cell without a nucleus has NaN
  `cytoplasm_area` and NaN layers; a cell its nuclei fill has `cytoplasm_area` 0. The full table is
  in [output](../reference/output.md#spatialdata-directory).
- **Nuclei come from the same method.** Cellpose segments nuclei on the last of
  `cellpose_channels` (or the projection's `nuclear`); InstanSeg on `dna` channels unless
  `instanseg_channels` is set.
- **Areas may differ slightly** between linking and the stored shapes, where a polygon needed
  repair. Repairing once, at resolve, is planned.
- **Two methods with two targets** cost four segmentations.

% source: docs/decisions.md#segmentation
% source: docs/usage.md#methods-and-targets
% source: ROADMAP.md#from-20

## Read more

- [The design](https://github.com/CosciaLab/histo/blob/dev/docs/superpowers/specs/2026-11-02-nuclei-cells-design.md),
  with the linking rules.
- [Shapely](https://shapely.readthedocs.io/), which does the geometry.
