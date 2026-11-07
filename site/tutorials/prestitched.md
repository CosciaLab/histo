# Tutorial 6: Pre-stitched image

## When to use

Your images were stitched elsewhere and you only want segmentation, quantification and QC. The
run starts at the [SpatialData store](../modules/spatialdata.md): no illumination correction,
stitching, dearray or background subtraction. The example below is made up; adapt it to your
images.

% source: docs/output.md#what-runs

## The samplesheet

One row per image:

| sample | data_path                               |
| ------ | --------------------------------------- |
| slideA | /data/myproject/stitched/slideA.ome.tif |
| slideB | /data/myproject/stitched/slideB.ome.tif |

:::{dropdown} Copy as CSV: `samplesheet.csv`

```csv
sample,data_path
slideA,/data/myproject/stitched/slideA.ome.tif
slideB,/data/myproject/stitched/slideB.ome.tif
```

:::

- `data_path` is the stitched OME-TIFF, the only format read.
- There is no marker sheet. Channel names come from the image itself, so name channels in
  `cellpose_channels` as the image does. An image without names gives `Channel:0:0`, and so on.
- That includes this pipeline's own stitched images from [Tutorial 5](stitching-only.md):
  Ashlar writes no channel names, so add them to the image first.

Columns: [The samplesheet](../inputs/samplesheet.md).

% source: assets/schema_input.json
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:124-146
% source: modules/local/utils.nf:217-225
% source: docs/decisions.md#channel-names

## The parameters

Save as `params.yml`:

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

- [`use_preprocessing: false`](../inputs/parameters-full.md#use_preprocessing) starts from the
  stitched image. See [Which steps run](../inputs/parameters.md#which-steps-run).
- [`cellpose_channels`](../inputs/parameters-full.md#cellpose_channels) gives
  [Cellpose](../modules/cellpose.md) a membrane marker and the nuclear stain, nuclear last.
  [Channel projection](../modules/projection.md) is not available here: it needs the marker
  sheet. For [InstanSeg](../modules/instanseg.md), set
  [`instanseg_channels`](../inputs/parameters-full.md#instanseg_channels) for the same reason.
- The three thresholds are Cellpose's own values. Left unset, sopa's defaults tile the whole
  tissue into cells, whatever the image shows.
- `patch_width_pixel: 5000` assumes 25 000 × 25 000 pixels: 25 patches. See
  [Patch size](../inputs/parameters.md#patch-size).

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:652-655
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-676
% source: docs/usage.md#choosing-patch-width-pixel
% source: docs/usage.md#two-channel-segmentation-use-projection

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

See [Running on the cluster](../getting-started/usage-guide.md#running-on-the-cluster).

What runs: the [SpatialData store](../modules/spatialdata.md),
[tiled segmentation](../modules/tiling.md) with Cellpose,
[quantification](../modules/quantification.md) and the [QC report](../modules/qc-report.md).

% source: docs/usage.md#quick-start
% source: docs/output.md#what-runs

## What you get

```text
results/
├── slideA.zarr/
│   ├── images/      the image, channels named as in the file
│   ├── shapes/      image_patches, cellpose_cells
│   └── tables/      cellpose_table
├── slideB.zarr/
├── qc/              slideA_cellpose_qc_report.html, slideB_cellpose_qc_report.html, …
└── pipeline_info/
```

No `preprocessing/`. Every file: [Outputs](../outputs/outputs.md).

% source: docs/output.md#spatialdata-directory
% source: modules/local/publish_spatialdata/main.nf:5
% source: tests/default.nf.test:24-52

## What to check

1. "Channels" in [the QC report](../outputs/reports.md#the-qc-report): the names you expect,
   not `Channel:0:0`.
2. "Segmentation overlay" and "Cells per patch".
3. The outlines over the image; see [Viewers](../outputs/reports.md#viewers).

Something off? See [Common failures](../outputs/reports.md#common-failures).

% source: bin/qc_report.py:738
