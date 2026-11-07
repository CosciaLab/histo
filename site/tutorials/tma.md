# Tutorial 2: Tissue microarray

## What you will do

Run a tissue microarray (TMA): the stitched slide is cut into its cores, each core is segmented
and checked on its own, and the cores are merged back into one store per slide.

The data is MCMICRO's exemplar-002: a small TMA with four cores, three cycles of four channels.
Cycle 1 records only autofluorescence, the tissue's own glow, so this run also subtracts it from
the markers. [Tutorial 3](wsi-backsub.md) explains background subtraction in detail. This is the
same run the pipeline is tested with before every release.

% source: conf/test_exemplar002.config
% source: tools/fetch_exemplars.sh
% source: docs/decisions.md#the-tma-path

## Get the data

Three OME-TIFF files, 953 MB in total, from MCMICRO's public storage:

```bash
mkdir -p /path/to/exemplars/exemplar-002 && cd /path/to/exemplars/exemplar-002
for c in 01 02 03; do
    curl -fLO "https://mcmicro.s3.amazonaws.com/exemplars/002/exemplar-002/raw/exemplar-002-cycle-$c.ome.tiff"
done
```

% source: tools/fetch_exemplars.sh:36,79-84

## The samplesheet

One row per cycle. The sample is the whole slide; the cores are found by the pipeline.

| sample       | cycle_number | image_tiles                                                    | marker_sheet                               |
| ------------ | ------------ | -------------------------------------------------------------- | ------------------------------------------ |
| exemplar-002 | 1            | /path/to/exemplars/exemplar-002/exemplar-002-cycle-01.ome.tiff | /path/to/exemplars/markers_exemplar002.csv |
| exemplar-002 | 2            | /path/to/exemplars/exemplar-002/exemplar-002-cycle-02.ome.tiff | /path/to/exemplars/markers_exemplar002.csv |
| exemplar-002 | 3            | /path/to/exemplars/exemplar-002/exemplar-002-cycle-03.ome.tiff | /path/to/exemplars/markers_exemplar002.csv |

:::{dropdown} Copy as CSV: `samplesheet.csv`

```csv
sample,cycle_number,image_tiles,marker_sheet
exemplar-002,1,/path/to/exemplars/exemplar-002/exemplar-002-cycle-01.ome.tiff,/path/to/exemplars/markers_exemplar002.csv
exemplar-002,2,/path/to/exemplars/exemplar-002/exemplar-002-cycle-02.ome.tiff,/path/to/exemplars/markers_exemplar002.csv
exemplar-002,3,/path/to/exemplars/exemplar-002/exemplar-002-cycle-03.ome.tiff,/path/to/exemplars/markers_exemplar002.csv
```

:::

Columns: [The samplesheet](../inputs/samplesheet.md).

% source: tools/fetch_exemplars.sh:99-104
% source: assets/schema_input_cycle.json

## The marker sheet

Save as `markers_exemplar002.csv`;
[download it from GitHub](https://github.com/CosciaLab/histo/blob/dev/tests/exemplar_data/markers_exemplar002.csv).

```{include} ../_generated/exemplar/markers_exemplar002.md

```

- The cores are found on the first `dna` channel, `DNA_1`.
- `background` names the autofluorescence channel to subtract from each marker, and `exposure`
  scales it to the marker's exposure time.
- `remove` drops the three autofluorescence channels after subtraction: 12 channels become 9.

Columns: [The marker sheet](../inputs/markers.md).

% source: tests/exemplar_data/markers_exemplar002.csv
% source: tests/exemplar002.nf.test:8,73-81
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:450-455

## The parameters

Save as `params.yml`:

```yaml
input: /path/to/exemplars/samplesheet.csv
outdir: /path/to/results/exemplar-002

use_tma_dearray: true
tma_expected_cores: 4
tma_core_diameter_mm: 1.5

use_backsub: true

use_instanseg: true
instanseg_pixel_size: 0.65
segment_nuclei: true

patch_width_pixel: 2000
```

- [`use_tma_dearray`](../inputs/parameters-full.md#use_tma_dearray) cuts the slide into cores
  with [Coreograph](../modules/coreograph.md).
  [`tma_expected_cores`](../inputs/parameters-full.md#tma_expected_cores) is a count, not rows ×
  columns; with [`tma_core_diameter_mm`](../inputs/parameters-full.md#tma_core_diameter_mm) it
  lets the pipeline pick how much to shrink the image before looking for cores. See
  [TMA dearray](../inputs/parameters.md#tma-dearray).
- [`use_backsub`](../inputs/parameters-full.md#use_backsub) subtracts the autofluorescence with
  [backsub](../modules/backsub.md), on each core separately.
- [InstanSeg](../modules/instanseg.md) segments cells and, with
  [`segment_nuclei`](../inputs/parameters-full.md#segment_nuclei), nuclei too; the two are then
  [linked](../modules/linking.md). See [Methods and targets](../inputs/parameters.md#methods-and-targets).
- Cores are about 2900 pixels across, so `patch_width_pixel: 2000` gives 2 × 2 patches per core.

% source: conf/test_exemplar002.config
% source: docs/usage.md#tma-dearray
% source: subworkflows/local/preprocess_images/main.nf:55
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:695-704

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

On the MDC cluster add `mdc`. Set up your session first:
[Running on the cluster](../getting-started/usage-guide.md#running-on-the-cluster).

What runs: [BaSiCPy](../modules/basicpy.md) per cycle and [Ashlar](../modules/ashlar.md) once
for the slide; then [Coreograph](../modules/coreograph.md) tries five shrink factors and keeps
the one that best matches four cores of 1.5 mm. Everything after that runs once per core:
[backsub](../modules/backsub.md), the [SpatialData store](../modules/spatialdata.md),
[tiled segmentation](../modules/tiling.md), [linking](../modules/linking.md),
[quantification](../modules/quantification.md) and the [QC report](../modules/qc-report.md).
Finally the four cores are merged into one store, with one report for the slide.

% source: docs/usage.md#quick-start
% source: docs/output.md#what-runs
% source: tests/exemplar002.nf.test:46-75

## What you get

```text
/path/to/results/exemplar-002/
├── preprocessing/
│   ├── illumination/            exemplar-002_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   ├── registration/            exemplar-002.ome.tif, exemplar-002_ashlar_qc/
│   ├── dearray/                 exemplar-002_core001.ome.tif … core004
│   │   │                        exemplar-002_tma_map.tif, _coremask.tif, _centroids.txt
│   │   ├── masks/               exemplar-002_core001_mask.tif, … one per core
│   │   └── sweep/               exemplar-002_sweep.tsv, _sweep_overlays.png, _selection.json, …
│   └── background_subtraction/  exemplar-002_core001_backsub.ome.tif and .csv, … one per core
├── exemplar-002_merged.zarr/    all four cores in one store
├── exemplar-002_merge_manifest.json
├── qc/
│   ├── exemplar-002_instanseg_slide_report.html
│   ├── exemplar-002_core001_instanseg_qc_report.html, … one per core
│   ├── exemplar-002_core001_instanseg_qc.json, … one per core
│   └── exemplar-002_core001_instanseg_qc_images/, … one per core
└── pipeline_info/
```

In the merged store every element is prefixed by its core, for example
`exemplar-002_core001__instanseg_table`. Per-core stores are not kept. Every file is described in
[Outputs](../outputs/outputs.md).

% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory
% source: conf/modules.config:37-77
% source: tests/exemplar002.nf.test:31,121-134

## What to check

1. `preprocessing/dearray/sweep/exemplar-002_sweep_overlays.png`: the cores found at each shrink
   factor. Four round cores, none split or merged. The log warns when even the best factor is off.
2. `qc/exemplar-002_instanseg_slide_report.html`: it names any core that failed a check, and
   holds the stitching QC for the slide. See [The QC report](../outputs/reports.md#the-qc-report).
3. A failing core's own report next.
4. In a core's report, "Channels" lists nine names: no `AF488`, `AF555` or `AF647`.
5. `exemplar-002_merged.zarr` with the outlines over the image; see
   [Viewers](../outputs/reports.md#viewers).

A core missing, or two merged into one: see [Common failures](../outputs/reports.md#common-failures).

% source: docs/usage.md#tma-dearray
% source: docs/output.md#qc-report
% source: tests/exemplar002.nf.test:73-81,116-119
