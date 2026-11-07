# Tutorial 1: Your first run

## What you will do

Run the whole pipeline once on a small public dataset, with no optional steps: illumination
correction, stitching, one segmentation method, quantification and the QC report.

The data is MCMICRO's exemplar-001: three cycles of cyclic immunofluorescence, four channels each,
on a small piece of tissue, about the size of one TMA core. Stitched, it is about 3500 × 2600
pixels. It is the same data the pipeline is tested on before every release.

% source: conf/test_exemplar001.config
% source: tools/fetch_exemplars.sh
% source: docs/CONTRIBUTING.md#pre-release-tests-cluster-by-hand

## Get the data

The images are three OME-TIFF files, 191 MB in total, from MCMICRO's public storage. The full
dataset has ten cycles; this tutorial uses cycles 6, 7 and 8. Download them into a folder of
your own:

```bash
mkdir -p /path/to/exemplars/exemplar-001 && cd /path/to/exemplars/exemplar-001
for c in 06 07 08; do
    curl -fLO "https://mcmicro.s3.amazonaws.com/exemplars/001/exemplar-001/raw/exemplar-001-cycle-$c.ome.tiff"
done
```

Each file holds all the tiles of one cycle, as the microscope wrote them.

% source: tools/fetch_exemplars.sh:36,72-77

## The samplesheet

One row per cycle. The pipeline needs cycles numbered 1, 2, 3 without gaps, so the downloaded
cycles 6, 7 and 8 become 1, 2 and 3 here.

| sample       | cycle_number | image_tiles                                                    | marker_sheet                               |
| ------------ | ------------ | -------------------------------------------------------------- | ------------------------------------------ |
| exemplar-001 | 1            | /path/to/exemplars/exemplar-001/exemplar-001-cycle-06.ome.tiff | /path/to/exemplars/markers_exemplar001.csv |
| exemplar-001 | 2            | /path/to/exemplars/exemplar-001/exemplar-001-cycle-07.ome.tiff | /path/to/exemplars/markers_exemplar001.csv |
| exemplar-001 | 3            | /path/to/exemplars/exemplar-001/exemplar-001-cycle-08.ome.tiff | /path/to/exemplars/markers_exemplar001.csv |

:::{dropdown} Copy as CSV: `samplesheet.csv`

```csv
sample,cycle_number,image_tiles,marker_sheet
exemplar-001,1,/path/to/exemplars/exemplar-001/exemplar-001-cycle-06.ome.tiff,/path/to/exemplars/markers_exemplar001.csv
exemplar-001,2,/path/to/exemplars/exemplar-001/exemplar-001-cycle-07.ome.tiff,/path/to/exemplars/markers_exemplar001.csv
exemplar-001,3,/path/to/exemplars/exemplar-001/exemplar-001-cycle-08.ome.tiff,/path/to/exemplars/markers_exemplar001.csv
```

:::

Replace `/path/to/exemplars` with your folder. Every column is explained in
[The samplesheet](../inputs/samplesheet.md).

% source: tools/fetch_exemplars.sh:84-97
% source: assets/schema_input_cycle.json

## The marker sheet

One row per channel, across all cycles. Save it as `markers_exemplar001.csv` next to the
samplesheet; [download it from GitHub](https://github.com/CosciaLab/histo/blob/dev/tests/exemplar_data/markers_exemplar001.csv).

```{include} ../_generated/exemplar/markers_exemplar001.md

```

- Every cycle starts with its DNA stain, marked `dna` in `channel_role`. The pipeline uses it to
  align the cycles to each other.
- Marker names keep the original cycle numbers (`DNA_6` to `DNA_8`), so you can still tell which
  acquisition a channel came from.

Every column is explained in [The marker sheet](../inputs/markers.md).

% source: tests/exemplar_data/markers_exemplar001.csv
% source: tools/fetch_exemplars.sh:84-87
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-475

## The parameters

Save as `params.yml`:

```yaml
input: /path/to/exemplars/samplesheet.csv
outdir: /path/to/results/exemplar-001

use_instanseg: true
instanseg_pixel_size: 0.65

patch_width_pixel: 1500
```

- [`use_instanseg`](../inputs/parameters-full.md#use_instanseg) segments cells with
  [InstanSeg](../modules/instanseg.md). It reads every `dna` and `marker` channel of the marker
  sheet, so there are no channels to choose.
- [`instanseg_pixel_size`](../inputs/parameters-full.md#instanseg_pixel_size) is the size of
  one pixel in µm. For exemplar-001 it is 0.65, as recorded in the image's metadata.
- [`patch_width_pixel`](../inputs/parameters-full.md#patch_width_pixel) cuts the image into
  1500-pixel squares, here 3 × 2 patches, segmented side by side. See
  [Patch size](../inputs/parameters.md#patch-size).

Cells are segmented by default; nuclei are not. Everything else stays at its default: no
background subtraction, no TMA dearray.

% source: conf/test_exemplar001.config
% source: modules/local/utils.nf:196-201
% source: nextflow_schema.json (segment_cells default true)

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

`singularity` runs every step in its container, `size_small` sets the resources for images up to
about 50 GB, and `slurm` sends the steps to the cluster. On the MDC cluster add `mdc`. Set up
your session first: [Running on the cluster](../getting-started/usage-guide.md#running-on-the-cluster).

What runs, in order: [BaSiCPy](../modules/basicpy.md) once per cycle,
[Ashlar](../modules/ashlar.md) once, then the conversion to a
[SpatialData store](../modules/spatialdata.md), [tiled segmentation](../modules/tiling.md) with
InstanSeg on each patch, [quantification](../modules/quantification.md) and the
[QC report](../modules/qc-report.md).

% source: docs/usage.md#quick-start
% source: docs/usage.md#profiles
% source: docs/output.md#what-runs

## What you get

```text
/path/to/results/exemplar-001/
├── preprocessing/
│   ├── illumination/   exemplar-001_cycle1-dfp.ome.tif, -ffp.ome.tif; per cycle
│   └── registration/   exemplar-001.ome.tif, exemplar-001_ashlar_qc/
├── exemplar-001.zarr/
│   ├── images/         exemplar-001, the stitched image, channels named from the marker sheet
│   ├── shapes/         image_patches, instanseg_cells
│   └── tables/         instanseg_table, one row per cell
├── qc/
│   ├── exemplar-001_instanseg_qc_report.html
│   ├── exemplar-001_instanseg_qc.json
│   └── exemplar-001_instanseg_qc_images/
└── pipeline_info/
```

Every file is described in [Outputs](../outputs/outputs.md).

% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory
% source: docs/output.md#qc-report
% source: tests/exemplar001.nf.test:31-36,84-93
% source: conf/modules.config:15-35

## What to check

1. Open `qc/exemplar-001_instanseg_qc_report.html` in a browser. Start with "Stitching and
   registration": did all three cycles align? See [The QC report](../outputs/reports.md#the-qc-report).
2. In "Channels", the twelve names match the marker sheet.
3. "Nuclear stain across cycles" compares `DNA_6` with `DNA_8` per cell: a drop means cells were
   lost or bleached in later cycles.
4. "Segmentation overlay" and "Cells per patch": outlines sit on cells, and no patch inside the
   tissue is empty.
5. Open the store with the outlines over the image; see [Viewers](../outputs/reports.md#viewers).

If something looks wrong, see [Common failures](../outputs/reports.md#common-failures).

Next: [Tutorial 4](multiple-segmentations.md) runs two methods on the same data and compares them.

% source: docs/output.md#qc-report
% source: tests/exemplar001.nf.test:95-105
% source: bin/qc_report.py:765
