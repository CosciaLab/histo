# Outputs

What a finished run leaves in `--outdir`. Every file is described in
[output](../reference/output.md).

```text
<outdir>/
├── preprocessing/
│   ├── illumination/            BaSiCPy profiles, per cycle
│   ├── registration/            {sample}.ome.tif, the stitched image; {sample}_ashlar_qc/
│   ├── background_subtraction/  with use_backsub
│   └── dearray/                 with use_tma_dearray
├── {sample}.zarr/               the SpatialData store
├── qc/                          QC reports, metrics JSON, images
└── pipeline_info/               Nextflow reports, tool versions, parameters
```

% source: docs/output.md#pipeline-overview
% source: conf/modules.config:15-166
% source: modules/local/publish_spatialdata/main.nf:5

On a TMA, `{slide}_merged.zarr/` and `{slide}_merge_manifest.json` take the place of per-core
stores. With `preprocessing_only`, `preprocessing/` and `pipeline_info/` are the whole output.

% source: docs/output.md#spatialdata-directory
% source: docs/output.md#preprocessing

## The store

```text
{sample}.zarr/
├── images/
│   └── <image>          the stitched image, channels named from the marker sheet
├── shapes/
│   ├── image_patches    the segmentation patch grid
│   ├── {m}_cells        cell polygons
│   ├── {m}_nuclei       with segment_nuclei
│   └── {m}_cytoplasm    with both targets
└── tables/
    └── {m}_table        one row per cell; marker statistics, shape features
```

`{m}` is `cellpose` or `instanseg`, one set per method. Cell ids are the same in the shapes and
the table. Pre-stitched input keeps the channel names its image carries. The table's columns,
layers and NaN rules are in [output](../reference/output.md#spatialdata-directory).

% source: docs/output.md#spatialdata-directory
% source: subworkflows/local/segmentation/main.nf:183
% source: tests/exemplar001.nf.test:85
% source: docs/decisions.md#channel-names

Next:

- [What changes the outputs](what-changes-it.md): which parameter adds or removes what.
- [Visual QC](visual-qc.md): what to open, in which order and viewer.
