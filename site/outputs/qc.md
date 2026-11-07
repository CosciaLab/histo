# QC files

Everything under `qc/`, file by file. How to read the reports is in
[Plots and reports](reports.md); what the QC step does, in [QC report](../modules/qc-report.md).

QC runs per sample and method (`{m}` is `cellpose` or `instanseg`); on a TMA, per core and
method. `use_qc: false` skips all of it, Ashlar's QC included.

% source: docs/output.md#qc-report
% source: subworkflows/local/qc/main.nf:39-64

| File                                | When                         | Holds                                      |
| ----------------------------------- | ---------------------------- | ------------------------------------------ |
| `{sample}_{m}_qc_report.html`       | always                       | the QC report, for a person                |
| `{sample}_{m}_qc.json`              | always                       | the same numbers, for a script             |
| `{sample}_{m}_qc_images/`           | `use_qc_images` (default on) | the images the report embeds, as PNG files |
| `{sample}_comparison.html`, `.json` | both methods segment cells   | Cellpose against InstanSeg                 |
| `{sample}_projection.png`, `.json`  | `use_projection`             | what Cellpose saw                          |
| `{slide}_{m}_slide_report.html`     | `use_tma_dearray`            | one page per slide, comparing its cores    |

% source: docs/output.md#qc-report
% source: conf/modules.config:113-166

## The report

`{sample}_{m}_qc_report.html` is one self-contained file: no external scripts, fonts or network
access, so it opens offline and can be emailed or copied anywhere. Every chart has a table view
beneath it. Section by section: [The QC report](reports.md#the-qc-report).

% source: docs/output.md#qc-report

## The metrics

`{sample}_{m}_qc.json` holds every number in the report: per-channel intensity statistics on
every pixel of the full-resolution image, the cell-area distribution and the count of tiny cells,
whether the image, the table and the marker sheet agree on channel names, cells per patch, and
with `use_backsub` the channel statistics from before subtraction. With cells and nuclei, a
`linking` block counts cells by number of nuclei, unlinked nuclei, and cells without cytoplasm.

Read this file, not the HTML, when a script checks many runs. It sets no thresholds: deciding what
is bad is up to you.

% source: docs/output.md#qc-report
% source: bin/qc_metrics.py:1-5

## The images

`{sample}_{m}_qc_images/` holds the segmentation crops and cluster pictures embedded in the
report, as PNG files you can reuse in slides. Absent with `use_qc_images: false`, which also makes
QC much faster.

% source: docs/output.md#qc-report
% source: subworkflows/local/qc/main.nf:51-58

## The comparison

`{sample}_comparison.html` and `.json`, when both methods segment cells: cell counts, median
areas, the share of each method's cells matched one-to-one by the other, and both outlines on
the same crops. See [Comparison report](reports.md#comparison-report).

% source: bin/compare_segmentations.py:1-20

## The projection preview

`{sample}_projection.png` and `.json`, with `use_projection`: the two channels Cellpose
segmented, nuclear in magenta and cell in green, downsampled. The JSON lists the markers in each
channel and how often each is the brightest. `dominant` names any marker brightest in over half
of a channel; that marker then decides the channel alone. See
[Channel projection](../modules/projection.md).

% source: docs/output.md#qc-report

## The slide report

`{slide}_{m}_slide_report.html`, on a TMA: one page per slide and method, comparing the cores.
Open it before any core's own report. See [Slide report](reports.md#slide-report).

% source: docs/output.md#qc-report
% source: bin/merge_report.py

## Ashlar's QC

Not in `qc/`: it stays in `preprocessing/registration/{sample}_ashlar_qc/`, listed in
[Preprocessing](preprocessing.md#ashlar-qc). The report's "Stitching and registration" section
reads it.

% source: docs/output.md#qc-report
