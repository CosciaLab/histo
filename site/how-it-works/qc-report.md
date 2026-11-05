# QC report

## The idea

Each run checks itself and reports what it found, for a person and for a script. The QC measures
the image, the segmentation and the table, and reports numbers, not a verdict: it sets no
thresholds and returns no exit code. The numbers that would justify a threshold need more than one
dataset behind them.

% source: docs/output.md#qc-report
% source: bin/qc_report.py:1784-1790
% source: bin/qc_metrics.py:1-5

The checks follow the pipeline:

- **Channels**: intensity statistics on every pixel of the full-resolution image, zero pixels, and
  whether the image, the table and the marker sheet agree on channel names.
- **Nuclear stain across cycles**: the first against the last cycle's nuclear stain per cell, to
  see cell loss in later cycles.
- **Stitching and registration**: Ashlar's own QC; see [Ashlar](ashlar.md).
- **Before and after background subtraction**, when it ran.
- **Cells**: the area distribution and the count of tiny, degenerate cells (below 10 px²), and
  cells per patch laid out as the patch grid.
- **Linking**: cells by number of nuclei, unlinked nuclei, cells without cytoplasm.
- **Images** (`use_qc_images`): segmentation outlines on full-resolution crops across the density
  range, and a clustering of cells by marker mean with representative cells per cluster.

% source: docs/output.md#qc-report
% source: bin/qc_report.py:1615-1680
% source: bin/qc_metrics.py:674-679
% source: docs/decisions.md#channel-projection

:::{note} Figure pending
The top of an exemplar-001 QC report: cell count, integrity checks and the channel table, from
`qc/{sample}_cellpose_qc_report.html`.
:::

## Why this pipeline uses it

The pipeline must run unattended on colleagues' data, so problems have to be visible without
opening the store. The JSON is the contract for scripts; the HTML is for people, and is
self-contained so it can be copied anywhere and opened offline. A soft QC gate was considered and
deferred: there are few samples, and each user reads their own report.

% source: CLAUDE.md#1-who-i-am-and-what-i-need
% source: docs/output.md#qc-report
% source: ROADMAP.md#deferred-deliberately

## In this pipeline

```{include} ../_generated/modules/qc-report.md

```

- QC runs per sample and method; on a TMA, per core and method. It reads the store and never
  writes to it, so it runs alongside publishing.
- `QC_METRICS` writes `qc/{sample}_{method}_qc.json`. `QC_IMAGES`, the slow part, makes the crops
  and clusters. `QC_REPORT` renders the HTML. They are separate, so a slow or failed image step
  does not cost the metrics.
- `MERGE_REPORT` writes one page per TMA slide and method, comparing cores.
- `COMPARE_SEGMENTATIONS` runs when both methods segment cells: counts, median areas, the share of
  cells matched one-to-one at IoU ≥ 0.5, and both outlines on the same crops.
- File names and contents are listed in [output](../reference/output.md#qc-report).

% source: subworkflows/local/qc/main.nf:1-2
% source: subworkflows/local/qc/main.nf:39-64
% source: workflows/histo.nf:116-170
% source: docs/output.md#what-runs
% source: bin/compare_segmentations.py:1-20

What steers it:

- [`use_qc`](../reference/parameters.md#use_qc), default true: all of the above, and Ashlar's QC.
- [`use_qc_images`](../reference/parameters.md#use_qc_images), default true: off keeps the
  metrics and charts but drops the crops and clustering.
- Tuning of the image step (Leiden resolutions, arcsinh cofactor, number of crops) goes through
  `ext.args` for `QC_IMAGES` in `conf/modules.config`, not through parameters.

% source: nextflow_schema.json:474-494
% source: conf/modules.config:121-130
% source: docs/output.md#qc-report

## Caveats

- **Nothing fails on bad QC.** A run with poor segmentation still exits 0; read the report.
- **The clusters are not reproducible on our one test slide**: seed-to-seed agreement peaked at
  0.596, against a 0.9 floor, and the report says so.
- **Sections repeat** across the reports of each method and each core. An overhaul is planned.
- **`use_qc: false` must go in a params file.** On the command line, `--use_qc false` is refused
  at startup; see [output](../reference/output.md#qc-report).

% source: docs/output.md#qc-report
% source: ROADMAP.md#findings
% source: ROADMAP.md#then-qc-report-overhaul
% source: ROADMAP.md#known-limitations

## Read more

- [The QC files](../reference/output.md#qc-report), one by one.
- Ashlar's QC: [When stitching or registration looks wrong](../reference/usage.md#when-stitching-or-registration-looks-wrong).
