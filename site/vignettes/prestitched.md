# Pre-stitched image

## When to use

Your images were stitched elsewhere and you only want segmentation, quantification and QC. The
run starts at `TO_SPATIALDATA`: no illumination correction, stitching, dearray or background
subtraction. See [What runs](../reference/output.md#what-runs).

% source: docs/output.md#what-runs

## Inputs

`samplesheet.csv`, one row per sample:

```csv
sample,data_path
slideA,/data/myproject/stitched/slideA.ome.tif
slideB,/data/myproject/stitched/slideB.ome.tif
```

- `data_path` is the stitched OME-TIFF. It is the only format read.
- No marker sheet. Channel names come from the image itself, so name channels in
  `cellpose_channels` as the OME-XML does. An image without names gives `Channel:0:0`, … .

Columns: [Samplesheets](../reference/samplesheet.md).

% source: assets/schema_input.json
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:124-146
% source: modules/local/utils.nf:217-225
% source: docs/output.md:50-52
% source: site/outputs/visual-qc.md#common-failures

## Parameters

`params.yml`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_preprocessing: false

use_cellpose: true
cellpose_channels: "CD45 DAPI"
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0

patch_width_pixel: 5000
```

- [`use_preprocessing`](../reference/parameters.md#use_preprocessing) `false` is this route.
- `use_projection` is not available here; it needs the marker sheet. For InstanSeg, set
  [`instanseg_channels`](../reference/parameters.md#instanseg_channels) for the same reason.
- `patch_width_pixel` `5000` assumes 25 000 × 25 000 px: 25 patches. See
  [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel).

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:652-655
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-676
% source: docs/usage.md#choosing-patch-width-pixel
% source: site/how-it-works/cellpose.md#caveats

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

`size_small` covers stitched images up to ~50 GB. Set up the session first:
[Running on the cluster](../reference/usage.md#running-on-the-cluster).

% source: docs/usage.md#quick-start
% source: docs/usage.md#profiles
% source: docs/usage.md#running-on-the-cluster

## What you get

```text
results/
├── slideA.zarr/
│   ├── shapes/      cellpose_cells
│   └── tables/      cellpose_table
├── slideB.zarr/
├── qc/              slideA_cellpose_qc_report.html, slideB_cellpose_qc_report.html, …
└── pipeline_info/
```

No `preprocessing/`. Every file: [Outputs](../outputs/outputs.md).

% source: docs/output.md#spatialdata-directory
% source: modules/local/publish_spatialdata/main.nf:5
% source: docs/output.md#qc-report
% source: tests/default.nf.test:24-52

## Check

- The report's "Channels" section: names as you expect, not `Channel:0:0`. See
  [Common failures](../outputs/visual-qc.md#common-failures).
- "Segmentation overlay" and "Cells per patch"; see
  [The QC report](../outputs/visual-qc.md#id-1-the-qc-report).
- The outlines over the image, in [the store](../outputs/visual-qc.md#id-3-the-spatialdata-store).

% source: site/outputs/visual-qc.md#common-failures
% source: bin/qc_report.py:738
