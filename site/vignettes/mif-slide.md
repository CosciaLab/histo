# mIF slide: Cellpose and InstanSeg

## When to use

A cyclic mIF slide, when you want cells and nuclei, and want to see how Cellpose and InstanSeg
compare on your data. Route: the "mIF slide" column of
[What runs](../reference/output.md#what-runs).

% source: docs/output.md#what-runs

## Inputs

`samplesheet.csv`, one row per cycle:

```csv
sample,cycle_number,image_tiles,marker_sheet
slide01,1,/data/myproject/raw/slide01/cycle01.ome.tiff,/data/myproject/sheets/markers_slide01.csv
slide01,2,/data/myproject/raw/slide01/cycle02.ome.tiff,/data/myproject/sheets/markers_slide01.csv
```

`markers_slide01.csv`, one row per channel:

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter
1,1,DNA_1,dna,nuclear,DAPI
2,1,CD45,marker,membrane,FITC
3,1,PanCK,marker,cytoplasm,Cy3
4,1,CD3,marker,membrane,Cy5
5,2,DNA_2,dna,nuclear,DAPI
6,2,CD8,marker,membrane,FITC
7,2,CD68,marker,cytoplasm,Cy3
8,2,Ki67,marker,nuclear,Cy5
```

- The nuclear stain is first in each cycle, because Ashlar aligns every cycle on within-cycle
  channel 0 unless `-c` says otherwise.
- `channel_compartment` chooses the projection's cell channel by default: every `marker` with
  `membrane` or `cytoplasm`. Ki67 stays out. An optional `segmentation` column overrides this.

Column rules: [Inputs](../reference/usage.md#inputs) and [Samplesheets](../reference/samplesheet.md).

% source: assets/schema_input_cycle.json
% source: assets/schema_marker.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-475

## Parameters

`params.yml`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_cellpose: true
use_projection: true
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0

use_instanseg: true
instanseg_pixel_size: 0.65

segment_nuclei: true
patch_width_pixel: 3000
```

- [`use_projection`](../reference/parameters.md#use_projection) builds Cellpose's nuclear and
  cell channels from the marker sheet. The three thresholds are Cellpose's own; without them
  sopa's defaults tile the tissue into cells. See
  [Two-channel segmentation](../reference/usage.md#two-channel-segmentation-use-projection).
- [`instanseg_pixel_size`](../reference/parameters.md#instanseg_pixel_size) is your image's
  pixel size in µm. InstanSeg requires it.
- [`segment_nuclei`](../reference/parameters.md#segment_nuclei) adds nuclei to the default
  cells. Two methods with two targets are four segmentations per patch; see
  [Methods and targets](../reference/usage.md#methods-and-targets).
- [`patch_width_pixel`](../reference/parameters.md#patch_width_pixel) `3000` assumes a stitched
  image of about 30 000 × 20 000 px: about 70 patches. Each InstanSeg cells task then asks for about
  39 GB (8 channels). See [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel).

% source: docs/usage.md#two-channel-segmentation-use-projection
% source: docs/usage.md#methods-and-targets
% source: docs/usage.md#choosing-patch-width-pixel
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:646-650
% source: modules/local/utils.nf:173-182
% source: modules/local/utils.nf:196-201

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

`size_small` covers stitched images up to ~50 GB; this one is about 10 GB at 16 bit. Set up the
session first: [Running on the cluster](../reference/usage.md#running-on-the-cluster).

% source: docs/usage.md#quick-start
% source: docs/usage.md#profiles
% source: docs/usage.md#running-on-the-cluster

## What you get

```text
results/
├── preprocessing/
│   ├── illumination/   slide01_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   └── registration/   slide01.ome.tif, slide01_ashlar_qc/
├── slide01.zarr/
│   ├── images/         the image, channels named from the marker sheet
│   ├── shapes/         image_patches, cellpose_cells, cellpose_nuclei, cellpose_cytoplasm, …
│   └── tables/         cellpose_table, instanseg_table
├── qc/
│   ├── slide01_cellpose_qc_report.html, slide01_instanseg_qc_report.html
│   ├── slide01_cellpose_qc.json, slide01_instanseg_qc.json
│   ├── slide01_cellpose_qc_images/, slide01_instanseg_qc_images/
│   ├── slide01_comparison.html, slide01_comparison.json
│   └── slide01_projection.png, slide01_projection.json
└── pipeline_info/
```

An excerpt; every file: [Outputs](../outputs/outputs.md).

% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory
% source: modules/local/publish_spatialdata/main.nf:5
% source: docs/output.md#qc-report
% source: conf/modules.config:15-35
% source: conf/modules.config:93-166

## Check

- The report's "Stitching and registration" section first: did every cycle align? See
  [The QC report](../outputs/visual-qc.md#id-1-the-qc-report).
- `qc/slide01_projection.png`, what Cellpose saw, and `dominant` in the JSON; see
  [Common failures](../outputs/visual-qc.md#common-failures).
- `qc/slide01_comparison.html`: cell counts, median areas and the share of cells both methods
  agree on.
- "Nuclear stain across cycles" in the report: cells lost between cycles.
- The outlines over the image, in [the store](../outputs/visual-qc.md#id-3-the-spatialdata-store).

% source: docs/usage.md#when-stitching-or-registration-looks-wrong
% source: docs/output.md#qc-report
% source: site/outputs/visual-qc.md#common-failures
% source: bin/qc_report.py:765
