# Stitching only

## When to use

You want illumination-corrected, stitched and registered images, and nothing after: no
segmentation, quantification or sample QC. Ashlar's own QC stays. See
[What runs](../reference/output.md#what-runs).

% source: docs/usage.md#parameters
% source: docs/output.md#what-runs

## Inputs

`samplesheet.csv`, one row per cycle; two samples here:

```csv
sample,cycle_number,image_tiles,marker_sheet
slide01,1,/data/myproject/raw/slide01/cycle01.ome.tiff,/data/myproject/sheets/markers.csv
slide01,2,/data/myproject/raw/slide01/cycle02.ome.tiff,/data/myproject/sheets/markers.csv
slide02,1,/data/myproject/raw/slide02/cycle01.ome.tiff,/data/myproject/sheets/markers.csv
slide02,2,/data/myproject/raw/slide02/cycle02.ome.tiff,/data/myproject/sheets/markers.csv
```

`markers.csv`, one row per channel:

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter
1,1,DNA_1,dna,nuclear,DAPI
2,1,CD45,marker,membrane,FITC
3,1,PanCK,marker,cytoplasm,Cy5
4,2,DNA_2,dna,nuclear,DAPI
5,2,CD3,marker,membrane,FITC
6,2,CD68,marker,cytoplasm,Cy5
```

The marker sheet is still required and checked: Ashlar aligns every cycle on the same
within-cycle channel, and the run stops at startup unless it is `dna`. Column rules:
[Inputs](../reference/usage.md#inputs).

% source: assets/schema_input_cycle.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:150-161
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-475

## Parameters

`params.yml`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

preprocessing_only: true
```

- [`preprocessing_only`](../reference/parameters.md#preprocessing_only) ends the run after
  preprocessing. No segmentation method is needed.
- Add [`use_backsub`](../reference/parameters.md#use_backsub) or
  [`use_tma_dearray`](../reference/parameters.md#use_tma_dearray) to get those images too.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:657-661
% source: docs/output.md#what-runs

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
├── preprocessing/
│   ├── illumination/   slide01_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   └── registration/   slide01.ome.tif, slide01_ashlar_qc/, slide02.ome.tif, slide02_ashlar_qc/
└── pipeline_info/
```

Ashlar writes no channel names, so channels in these images are unnamed. Every file:
[Outputs](../outputs/outputs.md).

% source: docs/output.md#preprocessing
% source: conf/modules.config:15-35
% source: tests/preprocessing_only.nf.test:38-49
% source: docs/decisions.md#channel-names

## Check

There is no HTML report.

- `preprocessing/registration/slide01_ashlar_qc/slide01_ashlar_report.pdf`: per-tile maps.
- `overlay_cycleN.jpg` in the same folder: cycle 1 in magenta over a later cycle in green.
- `qc.json`, `edges.csv` and `tiles.csv` there for detail; see
  [When stitching or registration looks wrong](../reference/usage.md#when-stitching-or-registration-looks-wrong).
- `slide01.ome.tif` in a viewer; see
  [The stitched OME-TIFF](../outputs/visual-qc.md#id-2-the-stitched-ome-tiff).

% source: docs/output.md#preprocessing
% source: docs/output.md:115-116
% source: site/outputs/visual-qc.md#id-2-the-stitched-ome-tiff
