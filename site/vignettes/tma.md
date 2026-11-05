# TMA: dearrayed, InstanSeg

## When to use

A tissue microarray: each core is cut out, segmented and checked alone, then merged back per
slide. Route: the "TMA, dearrayed" column of [What runs](../reference/output.md#what-runs).

% source: docs/output.md#what-runs
% source: docs/decisions.md#the-tma-path

## Inputs

`samplesheet.csv`, one row per cycle. The sample is the slide:

```csv
sample,cycle_number,image_tiles,marker_sheet
TMA01,1,/data/myproject/raw/TMA01/cycle01.ome.tiff,/data/myproject/sheets/markers_TMA01.csv
TMA01,2,/data/myproject/raw/TMA01/cycle02.ome.tiff,/data/myproject/sheets/markers_TMA01.csv
```

`markers_TMA01.csv`, one row per channel:

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter
1,1,DNA_1,dna,nuclear,DAPI
2,1,CD45,marker,membrane,FITC
3,1,PanCK,marker,cytoplasm,Cy5
4,2,DNA_2,dna,nuclear,DAPI
5,2,CD3,marker,membrane,FITC
6,2,Ki67,marker,nuclear,Cy5
```

- Coreograph finds cores on the first `dna` channel, here `DNA_1`.
- InstanSeg reads the `dna` and `marker` channels for cells, and `dna` only for nuclei.

Column rules: [Inputs](../reference/usage.md#inputs) and [Samplesheets](../reference/samplesheet.md).

% source: assets/schema_input_cycle.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:450-455
% source: modules/local/utils.nf:196-201

## Parameters

`params.yml`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_tma_dearray: true
tma_expected_cores: 48
tma_core_diameter_mm: 1.0

use_instanseg: true
instanseg_pixel_size: 0.65

segment_nuclei: true
```

- [`tma_expected_cores`](../reference/parameters.md#tma_expected_cores) is a count, not rows ×
  columns. With [`tma_core_diameter_mm`](../reference/parameters.md#tma_core_diameter_mm) it
  picks Coreograph's downsample factor; both apply to every slide in the run. See
  [TMA dearray](../reference/usage.md#tma-dearray).
- [`instanseg_pixel_size`](../reference/parameters.md#instanseg_pixel_size) is your image's
  pixel size in µm. InstanSeg requires it.
- `patch_width_pixel` stays at its default, 2000, which suits TMA cores: a 1 mm core at
  0.65 µm/px is about 1500 px across.

% source: docs/usage.md#tma-dearray
% source: docs/usage.md#choosing-patch-width-pixel
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:646-650
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:695-704

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
│   ├── illumination/   TMA01_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   ├── registration/   TMA01.ome.tif, TMA01_ashlar_qc/
│   └── dearray/        TMA01_core001.ome.tif, … one per core; TMA01_tma_map.tif, masks/
│       └── sweep/      TMA01_sweep.tsv, TMA01_sweep_overlays.png, TMA01_selection.json
├── TMA01_merged.zarr/  every core, one store
├── TMA01_merge_manifest.json
├── qc/
│   ├── TMA01_instanseg_slide_report.html
│   └── TMA01_core001_instanseg_qc_report.html, … one per core
└── pipeline_info/
```

Per-core stores are not published. Every file: [Outputs](../outputs/outputs.md).

% source: docs/output.md#what-runs
% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory
% source: docs/output.md#qc-report
% source: conf/modules.config:15-77
% source: conf/modules.config:113-166
% source: modules/local/merge_spatialdata/main.nf:15-16
% source: modules/local/merge_report/main.nf:16

## Check

- `preprocessing/dearray/sweep/TMA01_sweep_overlays.png`: the cores found at each factor. The
  log warns when even the best factor is off.
- `preprocessing/dearray/TMA01_tma_map.tif` when a core is missing or two are merged; see
  [Common failures](../outputs/visual-qc.md#common-failures).
- `qc/TMA01_instanseg_slide_report.html` first: it names the cores that failed a check and holds
  the stitching QC. See [The QC report](../outputs/visual-qc.md#id-1-the-qc-report).
- A failing core's own report next.
- `TMA01_merged.zarr` in [napari-spatialdata](../outputs/visual-qc.md#id-3-the-spatialdata-store).

% source: docs/usage.md#tma-dearray
% source: docs/output.md#preprocessing
% source: docs/output.md#qc-report
% source: site/outputs/visual-qc.md#id-1-the-qc-report
