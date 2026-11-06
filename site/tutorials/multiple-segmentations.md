# Tutorial 4: Multiple segmentations

## What you will do

Segment the same tissue with two methods, [Cellpose](../modules/cellpose.md) and
[InstanSeg](../modules/instanseg.md), each finding both cells and nuclei, and compare the two.
Use this when you are unsure which method suits your tissue, or when you want nuclei and
cytoplasm measured separately.

The data is exemplar-001, as in [Tutorial 1](exemplar-001.md). Do that one first: the
download, samplesheet and marker sheet are the same.

% source: conf/test_exemplar001.config
% source: docs/usage.md#methods-and-targets

## Choose methods and targets

Pick one or both **methods**:

| You want                                   | Set                                                                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Cells from one membrane marker and DNA     | `use_cellpose: true`, `cellpose_channels: "CD45 DNA_6"`, nuclear stain last                                          |
| Cells from many markers, with Cellpose     | `use_cellpose: true`, `use_projection: true`; see [Many markers](../inputs/parameters.md#many-markers-with-cellpose) |
| Cells from every marker, no channel choice | `use_instanseg: true`, `instanseg_pixel_size` in µm per pixel                                                        |
| A second opinion                           | Both. The QC then compares them                                                                                      |

Then the **targets**. Cells are on by default.

| You want                            | Set                                            |
| ----------------------------------- | ---------------------------------------------- |
| Cells                               | nothing                                        |
| Cells, nuclei and cytoplasm, linked | `segment_nuclei: true`                         |
| Nuclei only                         | `segment_cells: false`, `segment_nuclei: true` |

Every method × target is one more pass over every patch. Two methods with two targets are four
segmentations per patch. Nuclei come from a nuclear stain: for Cellpose the last of
`cellpose_channels`, or the projection's nuclear channel; for InstanSeg the `dna` channels.
More: [Methods and targets](../inputs/parameters.md#methods-and-targets).

% source: docs/usage.md#methods-and-targets
% source: modules/local/utils.nf:57-68
% source: modules/local/utils.nf:196-201
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:642-668

## The parameters

Use the samplesheet and marker sheet from [Tutorial 1](exemplar-001.md). Save as `params.yml`:

```yaml
input: /path/to/exemplars/samplesheet.csv
outdir: /path/to/results/exemplar-001-both

use_cellpose: true
use_projection: true
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0

use_instanseg: true
instanseg_pixel_size: 0.65

segment_nuclei: true
patch_width_pixel: 1500
```

- [`use_projection`](../inputs/parameters-full.md#use_projection) gives Cellpose two channels
  built from the marker sheet ([Channel projection](../modules/projection.md)): `DNA_6` as
  nuclear, and every `marker` whose `channel_compartment` is `membrane` or `cytoplasm` as cell.
  `FOXP3` is nuclear, so it stays out.
- The three thresholds are Cellpose's own values. Left unset, sopa's defaults tile the whole
  tissue into cells, whatever the image shows.
- [`segment_nuclei`](../inputs/parameters-full.md#segment_nuclei) adds nuclei to the cells.
  Each nucleus is then [linked](../modules/linking.md) to its cell, and the cytoplasm is the cell
  minus its nuclei.
- With 1500-pixel patches, 3 × 2 patches, two methods and two targets: 24 segmentation tasks.
  Each InstanSeg cell task asks for about 16 GB of memory (12 channels).

% source: docs/usage.md#two-channel-segmentation-use-projection
% source: tests/exemplar_data/markers_exemplar001.csv
% source: conf/test_exemplar001.config
% source: docs/usage.md#choosing-patch-width-pixel

## Run

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

On the MDC cluster add `mdc`. See
[Running on the cluster](../getting-started/usage-guide.md#running-on-the-cluster).

% source: docs/usage.md#quick-start

## What you get

```text
/path/to/results/exemplar-001-both/
├── preprocessing/            as in Tutorial 1
├── exemplar-001.zarr/
│   ├── images/               exemplar-001
│   ├── shapes/               image_patches,
│   │                         cellpose_cells, cellpose_nuclei, cellpose_cytoplasm,
│   │                         instanseg_cells, instanseg_nuclei, instanseg_cytoplasm
│   └── tables/               cellpose_table, instanseg_table; layers nucleus and cytoplasm
├── qc/
│   ├── exemplar-001_cellpose_qc_report.html, exemplar-001_instanseg_qc_report.html
│   ├── exemplar-001_cellpose_qc.json, exemplar-001_instanseg_qc.json
│   ├── exemplar-001_cellpose_qc_images/, exemplar-001_instanseg_qc_images/
│   ├── exemplar-001_comparison.html, exemplar-001_comparison.json
│   └── exemplar-001_projection.png, exemplar-001_projection.json
└── pipeline_info/
```

Each method has its own table, one row per cell, with marker intensities over the whole cell
and, in the layers, over the nucleus and the cytoplasm. See
[The SpatialData store](../outputs/zarr.md).

% source: tests/exemplar001.nf.test:84-93,113-119
% source: docs/output.md#spatialdata-directory
% source: docs/output.md#qc-report

## What to check

1. `qc/exemplar-001_projection.png`, what Cellpose saw: nuclear in magenta, cell in green. In
   the JSON, a marker under `dominant` swamps the others; leave it out with the `segmentation`
   column of the marker sheet. See [Many markers](../inputs/parameters.md#many-markers-with-cellpose).
2. `qc/exemplar-001_comparison.html`: cell counts, median areas, and the share of cells both
   methods agree on, with both outlines on the same crops.
3. "Linking" in each method's report: cells by number of nuclei, nuclei linked to no cell, and
   cells their nucleus fills completely (no cytoplasm). See [The QC report](../outputs/reports.md#the-qc-report).
4. Both sets of outlines over the image; see [Viewers](../outputs/reports.md#viewers).

% source: docs/usage.md#two-channel-segmentation-use-projection
% source: bin/compare_segmentations.py:1-20
% source: site/modules/qc-report.md
