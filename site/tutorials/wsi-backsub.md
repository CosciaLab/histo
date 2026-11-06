# Tutorial 3: Whole slide with background subtraction

## When to use

A whole slide imaged with autofluorescence channels: a cycle, or channels, that record only the
tissue's own glow. [backsub](../modules/backsub.md) subtracts them from the markers before
segmentation. The example below is made up; adapt the names and paths to your slide.

% source: docs/output.md#what-runs
% source: site/modules/backsub.md

## The samplesheet

One row per cycle:

| sample | cycle_number | image_tiles                                | marker_sheet                             |
| ------ | ------------ | ------------------------------------------ | ---------------------------------------- |
| wsi01  | 1            | /data/myproject/raw/wsi01/cycle01.ome.tiff | /data/myproject/sheets/markers_wsi01.csv |
| wsi01  | 2            | /data/myproject/raw/wsi01/cycle02.ome.tiff | /data/myproject/sheets/markers_wsi01.csv |

:::{dropdown} Copy as CSV: `samplesheet.csv`

```csv
sample,cycle_number,image_tiles,marker_sheet
wsi01,1,/data/myproject/raw/wsi01/cycle01.ome.tiff,/data/myproject/sheets/markers_wsi01.csv
wsi01,2,/data/myproject/raw/wsi01/cycle02.ome.tiff,/data/myproject/sheets/markers_wsi01.csv
```

:::

Columns: [The samplesheet](../inputs/samplesheet.md).

% source: assets/schema_input_cycle.json

## The marker sheet

Cycle 1 records the background, cycle 2 the markers:

| channel_number | cycle_number | marker_name | channel_role     | channel_compartment | filter | exposure | background | remove |
| -------------- | ------------ | ----------- | ---------------- | ------------------- | ------ | -------- | ---------- | ------ |
| 1              | 1            | DNA_1       | dna              | nuclear             | DAPI   | 20       |            |        |
| 2              | 1            | AF_FITC     | autofluorescence |                     | FITC   | 100      |            | true   |
| 3              | 1            | AF_Cy5      | autofluorescence |                     | Cy5    | 150      |            | true   |
| 4              | 2            | DNA_2       | dna              | nuclear             | DAPI   | 20       |            |        |
| 5              | 2            | CD45        | marker           | membrane            | FITC   | 100      | AF_FITC    |        |
| 6              | 2            | PanCK       | marker           | cytoplasm           | Cy5    | 150      | AF_Cy5     |        |

:::{dropdown} Copy as CSV: `markers_wsi01.csv`

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter,exposure,background,remove
1,1,DNA_1,dna,nuclear,DAPI,20,,
2,1,AF_FITC,autofluorescence,,FITC,100,,true
3,1,AF_Cy5,autofluorescence,,Cy5,150,,true
4,2,DNA_2,dna,nuclear,DAPI,20,,
5,2,CD45,marker,membrane,FITC,100,AF_FITC,
6,2,PanCK,marker,cytoplasm,Cy5,150,AF_Cy5,
```

:::

- Every channel needs an `exposure`: the background is scaled by the ratio of exposure times.
- `background` names a channel whose `channel_role` is `autofluorescence`.
- `remove: true` drops the two background channels after subtraction. Keep at least one `dna`
  channel.

Columns: [The marker sheet](../inputs/markers.md).

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:316-363

## The parameters

Save as `params.yml`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_backsub: true

use_cellpose: true
cellpose_channels: "CD45 DNA_1"
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0

patch_width_pixel: 8000
```

- [`use_backsub`](../inputs/parameters-full.md#use_backsub) turns subtraction on. See
  [Background subtraction](../inputs/parameters.md#background-subtraction).
- [`cellpose_channels`](../inputs/parameters-full.md#cellpose_channels) gives
  [Cellpose](../modules/cellpose.md) one membrane marker and the DNA stain, nuclear stain last.
  A channel that `remove` drops cannot be used here; the run stops at the start if it is.
- The three thresholds are Cellpose's own values. Left unset, sopa's defaults tile the whole
  tissue into cells, whatever the image shows.
- `patch_width_pixel: 8000` assumes a stitched image of about 100 000 × 60 000 pixels: about 100
  patches. See [Patch size](../inputs/parameters.md#patch-size).

% source: docs/usage.md#parameters
% source: docs/usage.md#choosing-patch-width-pixel
% source: site/modules/cellpose.md

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_medium,slurm \
    -params-file params.yml
```

`size_medium` covers stitched images of about 50 to 200 GB; this one is about 72 GB at 16 bit.
See [Profiles](../getting-started/usage-guide.md#profiles).

What runs: [BaSiCPy](../modules/basicpy.md) per cycle, [Ashlar](../modules/ashlar.md),
[backsub](../modules/backsub.md), then the [SpatialData store](../modules/spatialdata.md),
[tiled segmentation](../modules/tiling.md) with Cellpose,
[quantification](../modules/quantification.md) and the [QC report](../modules/qc-report.md).

% source: docs/usage.md#profiles
% source: docs/output.md#what-runs

## What you get

```text
results/
├── preprocessing/
│   ├── illumination/            wsi01_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   ├── registration/            wsi01.ome.tif, wsi01_ashlar_qc/
│   └── background_subtraction/  wsi01_backsub.ome.tif, wsi01_backsub.csv
├── wsi01.zarr/
│   ├── images/                  wsi01_backsub, the subtracted image
│   ├── shapes/                  image_patches, cellpose_cells
│   └── tables/                  cellpose_table
├── qc/                          wsi01_cellpose_qc_report.html, wsi01_cellpose_qc.json,
│                                wsi01_cellpose_qc_images/
└── pipeline_info/
```

Every file: [Outputs](../outputs/outputs.md).

% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory
% source: conf/modules.config:37-47

## What to check

1. `preprocessing/background_subtraction/wsi01_backsub.csv`: the marker sheet everything after
   subtraction reads. The background channels are gone and `channel_number` is renumbered.
2. "Zero pixels per channel" in [the QC report](../outputs/reports.md#the-qc-report), before
   and after subtraction. Many zero pixels after means real signal was subtracted away.
3. `wsi01.ome.tif` beside `wsi01_backsub.ome.tif` in a viewer; see
   [Viewers](../outputs/reports.md#viewers).
4. "Segmentation overlay" and "Cells per patch"; see
   [Common failures](../outputs/reports.md#common-failures).

% source: docs/output.md#preprocessing
% source: bin/qc_report.py:695-720
% source: bin/qc_report.py:752
