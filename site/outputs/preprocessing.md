# Preprocessing outputs

Everything under `preprocessing/`: what the first half of the pipeline made from the raw cycles.
None of it exists for a [pre-stitched](../tutorials/prestitched.md) run.

% source: docs/output.md#preprocessing
% source: docs/output.md#what-runs

## Illumination profiles

`preprocessing/illumination/{sample}_cycle{n}-dfp.ome.tif` and `-ffp.ome.tif`: the dark-field
and flat-field profiles [BaSiCPy](../modules/basicpy.md) computed for each cycle, one plane per
channel. Ashlar applies them while stitching.

- Absent for a cycle whose profiles you gave in the samplesheet: nothing was computed.
- Reuse them in a later run through the samplesheet's `dfp` and `ffp` columns; see
  [Samplesheet](../inputs/samplesheet.md).
- The dark-field is not fitted, so the `-dfp` file holds no fitted dark-field.

% source: docs/output.md#preprocessing
% source: bin/basicpy_main.py:108-115
% source: bin/basicpy_main.py:322-335

## Stitched image

`preprocessing/registration/{sample}.ome.tif`: the stitched and registered image from
[Ashlar](../modules/ashlar.md), all cycles in one pyramidal OME-TIFF. It is the handoff between
the two halves of the pipeline, and **the first file to open when segmentation looks wrong**.

- Channels are unnamed here; names from the marker sheet are added only in the store.
- The pixel size is in this file's metadata. The store does not carry it.
- With `use_backsub` or `use_tma_dearray`, the store is built from the later image below, not
  this one.

% source: docs/output.md#preprocessing
% source: docs/decisions.md#channel-names
% source: docs/decisions.md#pixel-size
% source: subworkflows/local/preprocess_images/main.nf:106-130

## Ashlar QC

`preprocessing/registration/{sample}_ashlar_qc/`, with `use_qc`: Ashlar's own account of how it
stitched and registered. On a TMA it is per slide, because Ashlar runs before the cores are cut.

| File                         | Holds                                                                            |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `qc.json`                    | the summary                                                                      |
| `{sample}_ashlar_report.pdf` | per-tile maps; the place to check stitching when there is no HTML report         |
| `overlay_cycleN.jpg`         | cycle 1 in magenta over a later cycle in green; grey where they align            |
| `thumb_cycleN.jpg`           | a thumbnail of each cycle                                                        |
| `edges.csv`                  | one row per neighbouring tile pair in cycle 1: shift, error, why it was rejected |
| `tiles.csv`                  | one row per tile per cycle: position, residual, angle, why it was discarded      |
| `null_errors.csv`            | errors of random non-overlapping strips, which set the rejection threshold       |
| `ashlar.log`                 | Ashlar's console output                                                          |

Ashlar counts cycles from 0 in the JSON and CSVs; the reports count from 1. The QC report's
"Stitching and registration" section reads this folder. What to change when it looks wrong:
[Ashlar](../modules/ashlar.md#when-stitching-looks-wrong).

% source: docs/output.md#preprocessing
% source: bin/qc_report.py:980-1210

## Background subtraction

`preprocessing/background_subtraction/`, with `use_backsub`:

- `{sample}_backsub.ome.tif`: the image after [backsub](../modules/backsub.md) subtracted the
  autofluorescence channels.
- `{sample}_backsub.csv`: backsub's own marker sheet. Rows marked `remove` are gone and
  `channel_number` is renumbered, so this is the sheet that describes the image everything
  downstream reads.

The `_backsub` suffix also names the image in the store, so cell ids start with it.

% source: docs/output.md#preprocessing
% source: site/outputs/outputs.md#what-changes-the-outputs

## TMA dearray

`preprocessing/dearray/`, with `use_tma_dearray`: the cores [Coreograph](../modules/coreograph.md)
cut out of each slide.

| File                                | Holds                              |
| ----------------------------------- | ---------------------------------- |
| `{slide}_core001.ome.tif`, …        | one image per core                 |
| `masks/{slide}_core001_mask.tif`, … | each core's mask                   |
| `{slide}_tma_map.tif`               | the slide with every core numbered |
| `{slide}_coremask.tif`              | all core masks on the slide        |
| `{slide}_centroids.txt`             | core centres                       |

The TMA map and the centroids are what to check when a core is missing or two cores became one.
Core names come from the slide name, so a slide run with and without background subtraction
gives cores with the same names.

`preprocessing/dearray/sweep/`, unless `coreograph_args` is set: the pipeline tries several
downsample factors and keeps the one whose cores best match your expected count and diameter.

| File                                                                           | Holds                                                                               |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `{slide}_sweep_overlays.png`                                                   | the cores found at every factor, side by side: **look at this first**               |
| `{slide}_sweep.tsv`                                                            | one row per factor, best first: core count, median diameter, spread, score, warning |
| `{slide}_selection.json`                                                       | the factor chosen                                                                   |
| `{slide}_k{k}_overlay.png`, `_metrics.json`, `_coremask.tif`, `_centroids.txt` | each factor's own result                                                            |

% source: docs/output.md#preprocessing
% source: conf/modules.config:49-78
