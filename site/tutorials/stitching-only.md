# Tutorial 5: Stitching only

## When to use

You want illumination-corrected, stitched and registered images, and nothing after: no
segmentation, quantification or QC report. Ashlar's own stitching QC is still written. The
example below is made up; adapt it to your slides.

% source: docs/usage.md#parameters
% source: docs/output.md#what-runs

## The samplesheet

One row per cycle; two slides here:

| sample  | cycle_number | image_tiles                                  | marker_sheet                       |
| ------- | ------------ | -------------------------------------------- | ---------------------------------- |
| slide01 | 1            | /data/myproject/raw/slide01/cycle01.ome.tiff | /data/myproject/sheets/markers.csv |
| slide01 | 2            | /data/myproject/raw/slide01/cycle02.ome.tiff | /data/myproject/sheets/markers.csv |
| slide02 | 1            | /data/myproject/raw/slide02/cycle01.ome.tiff | /data/myproject/sheets/markers.csv |
| slide02 | 2            | /data/myproject/raw/slide02/cycle02.ome.tiff | /data/myproject/sheets/markers.csv |

:::{dropdown} Copy as CSV: `samplesheet.csv`

```csv
sample,cycle_number,image_tiles,marker_sheet
slide01,1,/data/myproject/raw/slide01/cycle01.ome.tiff,/data/myproject/sheets/markers.csv
slide01,2,/data/myproject/raw/slide01/cycle02.ome.tiff,/data/myproject/sheets/markers.csv
slide02,1,/data/myproject/raw/slide02/cycle01.ome.tiff,/data/myproject/sheets/markers.csv
slide02,2,/data/myproject/raw/slide02/cycle02.ome.tiff,/data/myproject/sheets/markers.csv
```

:::

% source: assets/schema_input_cycle.json

## The marker sheet

| channel_number | cycle_number | marker_name | channel_role | channel_compartment | filter |
| -------------- | ------------ | ----------- | ------------ | ------------------- | ------ |
| 1              | 1            | DNA_1       | dna          | nuclear             | DAPI   |
| 2              | 1            | CD45        | marker       | membrane            | FITC   |
| 3              | 1            | PanCK       | marker       | cytoplasm           | Cy5    |
| 4              | 2            | DNA_2       | dna          | nuclear             | DAPI   |
| 5              | 2            | CD3         | marker       | membrane            | FITC   |
| 6              | 2            | CD68        | marker       | cytoplasm           | Cy5    |

:::{dropdown} Copy as CSV: `markers.csv`

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter
1,1,DNA_1,dna,nuclear,DAPI
2,1,CD45,marker,membrane,FITC
3,1,PanCK,marker,cytoplasm,Cy5
4,2,DNA_2,dna,nuclear,DAPI
5,2,CD3,marker,membrane,FITC
6,2,CD68,marker,cytoplasm,Cy5
```

:::

The marker sheet is still required and checked. [Ashlar](../modules/ashlar.md) aligns every
cycle on the same position within the cycle, and the run stops at the start unless that channel
is `dna`. Columns: [The marker sheet](../inputs/markers.md).

% source: assets/schema_marker.json
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:150-161
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-475

## The parameters

Save as `params.yml`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

preprocessing_only: true
```

- [`preprocessing_only`](../inputs/parameters-full.md#preprocessing_only) ends the run after
  [BaSiCPy](../modules/basicpy.md) and [Ashlar](../modules/ashlar.md). No segmentation method is
  needed. See [Which steps run](../inputs/parameters.md#which-steps-run).
- Add [`use_backsub`](../inputs/parameters-full.md#use_backsub) or
  [`use_tma_dearray`](../inputs/parameters-full.md#use_tma_dearray) to get those images too.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:657-661
% source: docs/output.md#what-runs

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

See [Running on the cluster](../getting-started/usage-guide.md#running-on-the-cluster).

% source: docs/usage.md#quick-start

## What you get

```text
results/
├── preprocessing/
│   ├── illumination/   slide01_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   └── registration/   slide01.ome.tif, slide01_ashlar_qc/, slide02.ome.tif, slide02_ashlar_qc/
└── pipeline_info/
```

Ashlar writes no channel names, so the channels in these images are unnamed. Every file:
[Preprocessing outputs](../outputs/preprocessing.md).

% source: docs/output.md#preprocessing
% source: tests/preprocessing_only.nf.test:38-49
% source: docs/decisions.md#channel-names

## What to check

There is no HTML report.

1. `preprocessing/registration/slide01_ashlar_qc/slide01_ashlar_report.pdf`: per-tile maps.
2. `overlay_cycleN.jpg` in the same folder: cycle 1 in magenta over a later cycle in green. Where
   they line up the two colours add to white; magenta and green fringes mean an offset.
3. `slide01.ome.tif` in a viewer; see [Viewers](../outputs/reports.md#viewers).

Misaligned? See [When stitching looks wrong](../modules/ashlar.md#when-stitching-looks-wrong).
This route is the fastest way to try new Ashlar settings.

% source: docs/output.md#preprocessing
% source: docs/output.md:115-116
