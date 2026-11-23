# QC report

## What it does

Every run checks its own result: the image, the segmentation and the table. It writes the numbers
as a web page for you to read and a JSON file for scripts. It reports numbers, not a verdict:
nothing fails on bad QC, so read the report.

% source: docs/output.md#qc-report
% source: bin/qc_report.py:1784-1790
% source: bin/qc_metrics.py:1-5

## Parameters

- [`use_qc`](../inputs/parameters-full.md#use_qc), default on: everything on this page, and
  Ashlar's stitching report. To turn it off, write `use_qc: false` in your `params.yml`; on the
  command line it is refused.
- [`use_qc_images`](../inputs/parameters-full.md#use_qc_images), default on: off keeps the
  numbers and charts but drops the image crops and the clustering, which take minutes rather than
  seconds.

More in [Quality control](../inputs/parameters.md#quality-control).

% source: nextflow_schema.json:474-494
% source: docs/output.md#qc-report

## How it works

The checks follow the pipeline:

- **Channels**: intensity statistics on every pixel of the full-resolution image, zero pixels, and
  whether the image, the table and the marker sheet agree on channel names.
- **Nuclear stain across cycles**: the first against the last cycle's nuclear stain per cell, to
  see cells lost in later cycles.
- **Stitching and registration**: Ashlar's own report; see [Ashlar](ashlar.md).
- **Before and after background subtraction**, when it ran.
- **Cells**: the area distribution, the count of tiny cells (below 10 px²), and cells per patch
  laid out as the patch grid.
- **Linking**: cells by number of nuclei, unlinked nuclei, and cells their nuclei fill.
- **Images** (`use_qc_images`): outlines on full-resolution crops across the density range, and
  a clustering of cells by marker mean with example cells per cluster. The clusters are not yet
  reproducible from run to run, and the report says so.

% source: docs/output.md#qc-report
% source: bin/qc_report.py:1615-1680
% source: bin/qc_metrics.py:674-679
% source: bin/qc_metrics.py:200-211
% source: ROADMAP.md#findings

:::{note} Figure pending
The top of an exemplar-001 QC report: cell count, integrity checks and the channel table, from
`qc/{sample}_cellpose_qc_report.html`.
:::

QC runs per sample and method (per core on a TMA), reads the store and never changes it. On a TMA,
a slide report compares the cores. When both methods segment cells, a comparison page shows their
counts, median areas, the share of cells matched one-to-one (overlap of at least half, IoU ≥ 0.5),
and both outlines on the same crops.

% source: subworkflows/local/qc/main.nf:1-64
% source: workflows/histo.nf:116-170
% source: bin/compare_segmentations.py:1-20

**Inputs and outputs.** In: the finished store, Ashlar's QC folder, and the image before
background subtraction when it ran. Out, under `qc/`: `{sample}_{method}_qc_report.html`, a
self-contained page you can copy anywhere and open offline; `{sample}_{method}_qc.json`; the
image crops; and `{sample}_comparison.html` or `{slide}_{method}_slide_report.html` when they
apply. File by file: [QC files](../outputs/qc.md). What each chart means:
[Reports](../outputs/reports.md#the-qc-report).

% source: docs/output.md#qc-report
% source: docs/output.md#what-runs

## Similar tools

- **MultiQC** collects the logs of standard tools into one report; it has no checks for
  segmented images.
- **Looking by eye** in napari or QuPath, which the report does not replace; see
  [Reports](../outputs/reports.md).

The report is written for this pipeline, so problems are visible without opening the store. A
pass/fail threshold was considered and deferred: the numbers that would justify one need more than
one dataset behind them.

% source: docs/output.md#qc-report
% source: ROADMAP.md#deferred-deliberately
% source: https://multiqc.info

## Read more

- [QC files](../outputs/qc.md), one by one, and [Reports](../outputs/reports.md).
- [When stitching looks wrong](ashlar.md#when-stitching-looks-wrong).

Version used:

```{include} ../_generated/modules/qc-report.md

```
