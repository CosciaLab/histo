# WSI with background subtraction

## When to use

A whole slide imaged with autofluorescence channels, which you want subtracted from the markers
before segmentation. Route: the "WSI, background subtracted" column of
[What runs](../reference/output.md#what-runs).

% source: docs/output.md#what-runs
% source: site/how-it-works/backsub.md#the-idea

## Inputs

`samplesheet.csv`, one row per cycle:

```csv
sample,cycle_number,image_tiles,marker_sheet
wsi01,1,/data/myproject/raw/wsi01/cycle01.ome.tiff,/data/myproject/sheets/markers_wsi01.csv
wsi01,2,/data/myproject/raw/wsi01/cycle02.ome.tiff,/data/myproject/sheets/markers_wsi01.csv
```

`markers_wsi01.csv`, one row per channel. Cycle 1 records the background, cycle 2 the markers:

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter,exposure,background,remove
1,1,DNA_1,dna,nuclear,DAPI,20,,
2,1,AF_FITC,autofluorescence,,FITC,100,,true
3,1,AF_Cy5,autofluorescence,,Cy5,150,,true
4,2,DNA_2,dna,nuclear,DAPI,20,,
5,2,CD45,marker,membrane,FITC,100,AF_FITC,
6,2,PanCK,marker,cytoplasm,Cy5,150,AF_Cy5,
```

- Every channel needs an `exposure`: backsub scales the background by the exposure ratio.
- `background` names a channel whose `channel_role` is `autofluorescence`.
- `remove: true` drops the two background channels after subtraction. Keep at least one `dna`
  channel.

Column rules: [Inputs](../reference/usage.md#inputs) and [backsub](../how-it-works/backsub.md).

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:316-363
% source: site/how-it-works/backsub.md#the-idea

## Parameters

`params.yml`:

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

- [`use_backsub`](../reference/parameters.md#use_backsub) turns the step on.
- [`cellpose_channels`](../reference/parameters.md#cellpose_channels): marker names, nuclear
  last. A removed channel here stops the run at startup.
- The three thresholds are Cellpose's own; without them sopa's defaults tile the tissue into cells. See
  [Cellpose](../how-it-works/cellpose.md#caveats).
- `patch_width_pixel` `8000` assumes a stitched image of about 100 000 × 60 000 px: about 100
  patches. See [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel).

% source: docs/usage.md#parameters
% source: docs/usage.md#inputs
% source: site/how-it-works/cellpose.md#caveats
% source: docs/usage.md#choosing-patch-width-pixel

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_medium,slurm \
    -params-file params.yml
```

`size_medium` covers stitched images of ~50–200 GB; this one is about 72 GB at 16 bit. Set up
the session first: [Running on the cluster](../reference/usage.md#running-on-the-cluster).

% source: docs/usage.md#quick-start
% source: docs/usage.md#profiles
% source: docs/usage.md#running-on-the-cluster

## What you get

```text
results/
├── preprocessing/
│   ├── illumination/            wsi01_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   ├── registration/            wsi01.ome.tif, wsi01_ashlar_qc/
│   └── background_subtraction/  wsi01_backsub.ome.tif, wsi01_backsub.csv
├── wsi01.zarr/
│   ├── images/                  the background-subtracted image
│   ├── shapes/                  image_patches, cellpose_cells
│   └── tables/                  cellpose_table
├── qc/                          wsi01_cellpose_qc_report.html, wsi01_cellpose_qc.json,
│                                wsi01_cellpose_qc_images/
└── pipeline_info/
```

An excerpt; every file: [Outputs](../outputs/outputs.md).

% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory
% source: modules/local/publish_spatialdata/main.nf:5
% source: docs/output.md#qc-report
% source: conf/modules.config:15-47
% source: conf/modules.config:113-166

## Check

- `preprocessing/background_subtraction/wsi01_backsub.csv`: the sheet everything downstream
  reads. The background channels are gone and `channel_number` is renumbered.
- "Zero pixels per channel" in [the QC report](../outputs/visual-qc.md#id-1-the-qc-report):
  before and after subtraction. Many zero pixels after means signal was subtracted away.
- `wsi01.ome.tif` beside `wsi01_backsub.ome.tif` in a viewer; see
  [The stitched OME-TIFF](../outputs/visual-qc.md#id-2-the-stitched-ome-tiff).
- "Segmentation overlay" and "Cells per patch" in the report; see
  [Common failures](../outputs/visual-qc.md#common-failures).

% source: docs/output.md#preprocessing
% source: bin/qc_report.py:695-720
% source: bin/qc_report.py:752
% source: site/outputs/visual-qc.md#common-failures
