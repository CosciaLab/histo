# Segmentation benchmark

Cellpose-SAM segments a prepared image, and the preparation is set by parameters: smoothing,
contrast enhancement, which channels form the cell image, and two thresholds. Until v3.2 these were
sopa's defaults or our guesses, never checked against cells drawn by hand. This benchmark checked
them, and the Cellpose defaults now come from it.

% source: docs/decisions.md#segmentation-benchmark

## What we did

We segmented images that experts had outlined by hand, under 475 settings, and scored each
setting against the outlines.

- **Data.** Three annotated sets, none used to train the model except as noted:
  - Cross-platform mIF ([Aleynick et al. 2023](https://www.synapse.org/Synapse:syn27624812)):
    119 Vectra and 10 CODEX crops from 12 tissues. It decides.
  - TissueNet 1.1, test split [@doi:10.1038/s41587-021-01094-0]: 1324 tiles from 19 sources.
    It decides too, with a caveat: its training split trained Cellpose-SAM.
  - Tonsil mIF ([Zenodo](https://zenodo.org/records/22107836)): 10 crops, partly annotated, so a
    check only.
- **Score.** A predicted cell counts as found when it overlaps a drawn one by at least half
  (IoU 0.5). F1 balances cells found against cells invented; 1 is perfect. We report the mean F1
  over crops, for whole cells and for nuclei.
- **Model.** `cpsam_v2` at diameter 30, as the pipeline runs it.
- **Round 1, 168 settings: preprocessing.** Combining markers (max, mean), the low percentile
  (1, 50), projection smoothing and Gaussian blur (σ 0, 1, 2), CLAHE (off, 0.2), and two
  threshold pairs: sopa's and Cellpose's.
- **Round 2, 307 settings: thresholds and channels.** With round 1's best preprocessing, a grid
  of 7 `flow_threshold` × 8 `cellprob_threshold` values; three cell-channel choices (all, without
  autofluorescence, without nuclear markers too); and CLAHE 0.01, a value common in the
  literature.

% source: tools/segmentation_benchmark/README.md
% source: docs/decisions.md#segmentation-benchmark

## What we found

:::{figure} images/benchmark/old-vs-new.png
:alt: Bar chart of mean F1 with the old and the new defaults for cells and nuclei on three datasets; the new defaults are higher on all six.

Mean F1 with sopa's defaults and with the new ones. Cells on Cross-platform improve on 128 of 129
crops, by 0.20 on average.
:::

- **Smoothing hurts.** Each of projection smoothing and Gaussian blur lowered F1, and together
  more. Cellpose-SAM normalises each image itself and needs no help.
- **CLAHE hurts.** At 0.2 and at 0.01: it helped only at thresholds that find too few cells,
  where a lower `cellprob_threshold` does better.
- **`flow_threshold` barely matters from 0.6 up.** Values from 0.6 to 2 scored within 0.01.
- **`cellprob_threshold` matters, and targets disagree.** Cells do best between -3 and 0. Nuclei
  on Cross-platform want -1 or less, on TissueNet 0 or more.
- **Max and percentile 1**, the existing projection defaults, were already best.
- **Autofluorescence in the cell image costs a little** (0.012 F1 on Vectra), nuclear markers
  less (0.004). The default grouping leaves both out.

:::{figure} images/benchmark/thresholds.png
:alt: Four heatmaps of mean F1 over flow_threshold and cellprob_threshold, for cells and nuclei on Cross-platform and TissueNet; a solid box marks 0.6 and -1.

Mean F1 for each threshold pair. Solid box: the chosen pair; dashed: each panel's own best.
:::

% source: docs/decisions.md#segmentation-benchmark

## Why these defaults

The pipeline has one threshold pair for cells and nuclei. Before round 2 ran, we fixed the rule:
take the pair whose largest shortfall from each target's own best is smallest, over cells and
nuclei on Cross-platform and TissueNet. That pair is 0.6 and -1, within 0.065 of the best
everywhere; TissueNet nuclei pay the most.

| Parameter                                                            | Old (sopa) | New |
| -------------------------------------------------------------------- | ---------- | --- |
| [`flow_threshold`](inputs/parameters-full.md#flow_threshold)         | 2          | 0.6 |
| [`cellprob_threshold`](inputs/parameters-full.md#cellprob_threshold) | -6         | -1  |
| [`clip_limit`](inputs/parameters-full.md#clip_limit) (CLAHE)         | 0.2        | 0   |
| [`gaussian_sigma`](inputs/parameters-full.md#gaussian_sigma)         | 1          | 0   |
| [`projection_sigma`](inputs/parameters-full.md#projection_sigma)     | 1          | 0   |

To reproduce a run from before v3.2, set the old values and `pretrained_model: cpsam` in your
params file. InstanSeg is unaffected.

% source: bin/segment_patch.py:24-48
% source: nextflow.config:60-63

## Limits

- **Percentiles per crop.** The benchmark rescaled each crop on its own; the pipeline rescales on
  the whole slide.
- **One model, one metric.** `cpsam_v2` at diameter 30, F1 at IoU 0.5.
- **Nuclear smoothing** helped nuclei at Cellpose's old thresholds and was not tested at the new
  ones.
- **Your tissue may differ.** Check the "Segmentation overlay" of the
  [QC report](outputs/reports.md) on your first run.

## Read more

- [The benchmark code](https://github.com/CosciaLab/histo/tree/dev/tools/segmentation_benchmark),
  to rerun it on your own annotated crops.
- [decisions.md](https://github.com/CosciaLab/histo/blob/dev/docs/decisions.md#segmentation-benchmark).
- [Cellpose](modules/cellpose.md) and [Channel projection](modules/projection.md).
