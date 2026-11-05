# CosciaLab/histo: Output

## Introduction

This document describes the output produced by the pipeline.

## What runs

The three routes drawn as the metro map in the [README](../README.md#steps). Everything else is
off by default. Each column's segmentation is an example: any methods and targets fit any route.

Read down a column to get one run's process list, in order. The QC steps and
`COMPARE_SEGMENTATIONS` read the store without writing to it, so they run alongside publishing.

| Station                   |              mIF slide               | WSI, background subtracted |      TMA, dearrayed       |
| ------------------------- | :----------------------------------: | :------------------------: | :-----------------------: |
| Segmentation              | Cellpose + InstanSeg, cells + nuclei |      Cellpose, cells       | InstanSeg, cells + nuclei |
| `BASICPY`                 |                  x                   |             x              |             x             |
| `ASHLAR`                  |                  x                   |             x              |             x             |
| `COREOGRAPH`              |                                      |                            |             x             |
| `BACKSUB`                 |                                      |             x              |         optional          |
| `TO_SPATIALDATA`          |                  x                   |             x              |             x             |
| `SET_CHANNEL_NAMES`       |                  x                   |             x              |             x             |
| `MAKE_IMAGE_PATCHES`      |                  x                   |             x              |             x             |
| `SEGMENT_PATCH_CELLPOSE`  |          per patch × target          |         per patch          |                           |
| `SEGMENT_PATCH_INSTANSEG` |          per patch × target          |                            |    per patch × target     |
| `RESOLVE`                 |         per method × target          |             x              |        per target         |
| `LINK_COMPARTMENTS`       |              per method              |                            |             x             |
| `AGGREGATE`               |              per method              |             x              |             x             |
| `WRITE_SEGMENTATIONS`     |                  x                   |             x              |             x             |
| `MERGE_SPATIALDATA`       |                                      |                            |             x             |
| `PUBLISH_SPATIALDATA`     |                  x                   |             x              |       x, per slide        |
| `QC_METRICS`              |              per method              |             x              |             x             |
| `QC_IMAGES`               |              per method              |             x              |             x             |
| `QC_REPORT`               |              per method              |             x              |             x             |
| `COMPARE_SEGMENTATIONS`   |                  x                   |                            |                           |
| `MERGE_REPORT`            |                                      |                            |             x             |

Everything after `COREOGRAPH`, `BACKSUB` included, runs once per core on the TMA path.
`MERGE_SPATIALDATA` then puts one slide's cores back together, and `PUBLISH_SPATIALDATA`
publishes the result, so publication happens once per slide rather than once per core. The
per-core stores are not published: the merged store copies every element family and every table
out of them, prefixed by core, so publishing both would write the slide out twice.

Variations not in the table:

- `LINK_COMPARTMENTS` runs for a method with both targets (`segment_cells`, `segment_nuclei`).
  `COMPARE_SEGMENTATIONS` runs when both methods segment cells and `use_qc` is true.
- `TISSUE_SEGMENTATION` is off in all three runs. It sits before `MAKE_IMAGE_PATCHES`.
- `use_preprocessing = false` is a fourth entry point, for images arriving pre-stitched. It
  starts at `TO_SPATIALDATA` and skips `SET_CHANNEL_NAMES`, because such an image is assumed to
  carry its own channel names.
- Supplying illumination profiles in the samplesheet bypasses `BASICPY`.
- `preprocessing_only` ends every path at the preprocessing outputs.
- `use_projection` adds `PROJECT_CHANNELS` before `MAKE_IMAGE_PATCHES`; Cellpose segments the
  projection, and `WRITE_SEGMENTATIONS` removes it unless `keep_projection`.

## Pipeline overview

The directories listed below will be created in the results directory after the pipeline has finished. All paths are relative to the top-level results directory.

The pipeline is built using [Nextflow](https://www.nextflow.io/) and outputs the following information:

- [Preprocessing](#preprocessing) - Illumination profiles, the stitched image, and the optional background-subtracted and dearrayed images.
- [SpatialData directory](#spatialdata-directory) - Full [SpatialData](https://spatialdata.scverse.org/en/stable/) object with the segmented and aggregated data.
- [QC report](#qc-report) - Per-sample HTML summary of segmentation and aggregation
- [Pipeline information](#pipeline-information) - Report metrics generated during the workflow execution

### Preprocessing

<details markdown="1">
<summary>Output files</summary>

- `preprocessing/illumination/`
  - `{sample}_cycle{n}-dfp.ome.tif` and `-ffp.ome.tif`, the dark-field and flat-field profiles
    BaSiCPy fitted for each cycle. Absent for a cycle whose profiles were supplied in the
    samplesheet, since nothing was computed.
- `preprocessing/registration/`
  - `{sample}.ome.tif`, the stitched and registered mosaic from Ashlar. **This is the handoff
    boundary between the two halves of the pipeline**, and the file to inspect first when
    segmentation looks wrong.
  - `{sample}_ashlar_qc/`, Ashlar's own account of how it stitched and registered, when
    `use_qc` is true. On a TMA it is per slide, since Ashlar runs before dearraying.
    `qc.json` summarises it; `edges.csv` has one row per neighbouring tile pair in cycle 1
    (shift, error, why it was rejected), `tiles.csv` one row per tile per cycle (nominal and
    final position, residual, angle, why it was discarded), `null_errors.csv` the errors of
    random non-overlapping strips the rejection threshold comes from; `overlay_cycleN.jpg` puts
    cycle 1 in magenta over cycle N+1 in green at their final positions, beside each cycle's
    `thumb_cycleN.jpg`; `{sample}_ashlar_report.pdf` has per-tile maps; `ashlar.log` is the
    console output. Ashlar counts cycles from 0 in the JSON and CSVs; the reports count from 1.
    Written before the mosaic, so a failed write still leaves it in the task's work directory.
- `preprocessing/background_subtraction/`
  - `{sample}_backsub.ome.tif` and `{sample}_backsub.csv`. Only when `use_backsub` is true. The
    CSV is backsub's own marker sheet rather than a copy of the input: rows whose `remove` column
    was set are gone and `channel_number` is renumbered over what survives, so this is the sheet
    that describes the image everything downstream reads.
- `preprocessing/dearray/`
  - `{slide}_core001.ome.tif` and one per core, plus `masks/{slide}_core001_mask.tif`,
    `{slide}_coremask.tif`, `{slide}_tma_map.tif` and `{slide}_centroids.txt`. Only when
    `use_tma_dearray` is true. The TMA map and centroids are what to check when a core is missing
    or two cores were merged into one.
- `preprocessing/dearray/sweep/`
  - `{slide}_sweep.tsv`: one row per downsample factor, best first, with its core count,
    median diameter, size spread, score and any warning. `{slide}_sweep_overlays.png` shows
    the detected cores at every factor side by side. Only without `coreograph_args`.
  - `{slide}_selection.json` (the chosen factor), and per factor `{slide}_k{k}_metrics.json`,
    `_coremask.tif`, `_centroids.txt` and `_overlay.png`.

</details>

The `_backsub` suffix appears only on backsub's own two files. Core identity comes from the
slide name rather than from the filename it was cut out of, so a slide processed with and without
background subtraction produces cores with matching names.

With `preprocessing_only`, these files and `pipeline_info/` are the whole output. There is no
HTML report then, so `{sample}_ashlar_qc/{sample}_ashlar_report.pdf` is where to check stitching.

### SpatialData directory

<details markdown="1">
<summary>Output files</summary>

- `{sample}.zarr/`, per method `{m}` (`cellpose`, `instanseg`):
  - `images/`: the image. With `keep_projection`, also `<image>_projected`: the `nuclear` and
    `cell` channels Cellpose segmented, at full resolution.
  - `shapes/{m}_cells` (`segment_cells`): cell polygons, indexed by cell id.
  - `shapes/{m}_nuclei` (`segment_nuclei`): nucleus polygons. With both targets, its
    `linked_cell_id` names the cell holding at least half of the nucleus; null if none.
  - `shapes/{m}_cytoplasm` (both targets): each cell minus its linked nuclei, for cells with
    non-empty cytoplasm only, indexed by their cell ids.
  - `tables/{m}_table`: one row per cell, or per nucleus in a nuclei-only run. Below.
- `{slide}_merged.zarr/` and `{slide}_merge_manifest.json`
  - **Dearrayed slides only**, instead of per-core stores: every core's elements in one store,
    and the manifest of what was merged.

</details>

The `{sample}.zarr` directory contains a [SpatialData](https://spatialdata.scverse.org/en/stable/) object, where the `sample` name is either (i) specified by the samplesheet, or (ii) based on the name of the corresponding input directory.

Shapes and tables named `{cellpose,instanseg}_{cells,nuclei,cytoplasm,table}` belong to the
pipeline: each run replaces those it writes and removes the rest, logging each. Do not give your
own elements these names.

Cell ids are `{image}_{m}_cells_{n}` (`{image}_{m}_nuclei_{n}` for nuclei), unique within a
store: the shapes' index and the table's `obs_names` and `obs['cell_id']` are the same ids.
`{m}_table` holds:

- `X`: the statistics per marker over the whole cell (the nucleus in a nuclei-only run), after
  `expand_radius_ratio` if set, float32. `var_names` are `{marker}_{statistic}` (`CD3_mean`);
  `var` has columns `marker` and `statistic`. Statistics are set by `quantification_statistics`
  (default `mean,median,std`); `std` is the population SD.
- `layers['nucleus']`, `layers['cytoplasm']` (both targets): the same `var` over the cell's
  nucleus compartment (its linked nuclei, clipped to the cell) and over its cytoplasm.
- `obs`: `region` (`{m}_cells`, or `{m}_nuclei`), `cell_id`, `slide`, and `core_id` on a
  dearrayed TMA. Shape features of the unexpanded polygon, in px and px²: `cell_area`,
  `cell_perimeter`, `cell_circularity` (NaN below 30 px²), `cell_solidity`, `cell_eccentricity`,
  `cell_major_axis_length`, `cell_minor_axis_length`. With both targets also `n_nuclei` (linked
  nuclei), `nucleus_id` (the largest), `cytoplasm_area`, the same seven as `nucleus_*` over the
  nucleus compartment, and `nc_ratio` (`nucleus_area / cell_area`). A nuclei-only run has
  `nucleus_*` for its own rows and no `cell_*`.
- `obsm['spatial']`: centroids of the unexpanded cells.
- `uns['quantification']`: `statistics`, `tile_size` and `max_window_px`, the largest read window.
- `uns['segmentation']`: the settings each segmentation was requested with, keyed by name
  (`{m}_cells`, `{m}_nuclei`). Unset options are absent; sopa's defaults applied.
  `{m}_kwargs` is kept as given, as text, in `method_kwargs_extra`. Lists such as `channels`
  read back as numpy arrays of `StringDType`, not Python lists.

NaN means "not measured", 0 means "measured, nothing there":

| Cell                   | `layers`                   | `nucleus_area` | `cytoplasm_area` |
| ---------------------- | -------------------------- | -------------- | ---------------- |
| No linked nucleus      | `nucleus`, `cytoplasm` NaN | 0              | NaN              |
| Nuclei fill the cell   | `cytoplasm` NaN            | > 0            | 0                |
| Covers no pixel centre | `X` and both layers NaN    |                |                  |

Without a linked nucleus, the other `nucleus_*` shape columns and `nc_ratio` are NaN.

Cells are never dropped. A cell covering no pixel centre is left out of the QC clustering.

To select one statistic:

```python
adata[:, adata.var.statistic == "median"]
```

`slide` and `core_id` say where cells came from: `slide` is the sample name from the
samplesheet, `core_id` the core (e.g. `TMA01_core001`). Runs without dearraying have no
`core_id` column. Ids may repeat across stores, so keep these columns when concatenating tables
of several stores, and make `obs_names` unique (e.g. `anndata.concat(..., index_unique="-")`).

Refer to the [SpatialData docs](https://spatialdata.scverse.org/en/stable/) for usage details, or to the [documentation of `sopa` as a Python package](https://prism-oncology.github.io/sopa/).

`PUBLISH_SPATIALDATA` copies the store here, and exists only for that: it runs after the last
step that writes to the store.

#### From 1.x

| 1.x                                                  | 2.0                                          |
| ---------------------------------------------------- | -------------------------------------------- |
| `tables/table`                                       | `tables/{m}_table`                           |
| `shapes/cellpose_boundaries`, `instanseg_boundaries` | `shapes/{m}_cells`                           |
| `qc/{sample}_qc.json`, `_qc_report.html`             | `qc/{sample}_{m}_qc.json`, `_qc_report.html` |
| `qc/{sample}_qc_images/`                             | `qc/{sample}_{m}_qc_images/`                 |
| `qc/{slide}_slide_report.html`                       | `qc/{slide}_{m}_slide_report.html`           |
| `obs_names` renumbered by sopa                       | the cell ids of the shapes                   |
| a cell covering no pixel centre: `X` 0               | NaN                                          |

Removed parameters stop the run at startup: `use_stardist` and every StarDist option,
`instanseg_target` (use `segment_cells`, `segment_nuclei`), `min_intensity_ratio`,
`technology` and `aggregate_channels`. Cells crossing an image chunk edge were measured with a
shifted mask in 1.x, so their intensities change ([CHANGELOG](../CHANGELOG.md)).

#### From 2.x

- `obs['area']` is `obs['cell_area']` (`nucleus_area` in a nuclei-only run).
- Columns are per statistic: `adata[:, "CD3"]` is `adata[:, "CD3_mean"]`.
- `X` and the layers are float32.

### QC report

<details markdown="1">
<summary>Output files</summary>

- `qc/{sample}_{method}_qc.json`
  - Every QC metric as machine-readable JSON. **This is the file an unattended run should
    read.** Per-channel intensity statistics measured on every pixel of the full-resolution
    image, cell-area distribution and the count below a degenerate-cell threshold, channel-name
    agreement between the image, the table and the marker sheet, cells per segmentation patch,
    and — when background subtraction ran — the same channel statistics from before
    subtraction, so the two can be compared. That comparison is available on dearrayed slides
    too: `COREOGRAPH` runs before `BACKSUB`, so every core is subtracted on its own and keeps
    an unsubtracted twin of matching shape. With both targets, `linking`: cells by number of
    nuclei (0, 1, 2+), unlinked nuclei and cells without cytoplasm. It sets no thresholds and
    returns no exit code: the numbers that would justify a threshold need more than one dataset
    behind them.
- `qc/{sample}_{method}_qc_report.html`
  - The same metrics rendered for a person, plus the images. Self-contained: no external
    scripts, fonts or network access, so it can be copied anywhere and opened offline.
    Includes segmentation overlays at full resolution across the density range, a cross-cycle
    nuclear-stain comparison, Ashlar's stitching and registration QC (not on TMA cores; it is
    on the slide report), a Leiden clustering tree over a resolution sweep, the
    cluster-by-marker profile, and representative cells per cluster. Every chart has a table
    view beneath it.
- Stitching and registration QC
  - Not copied into `qc/`: the report's "Stitching and registration" section reads
    `preprocessing/registration/{sample}_ashlar_qc/` (above) and links to its PDF. It shows
    whether every tile pair aligned, whether the mosaic is one connected piece, how many tiles
    each cycle discarded and why, the residual misalignment per cycle, and the cycle overlays.
    See [usage.md](usage.md#when-stitching-or-registration-looks-wrong) for what to change.
- `qc/{sample}_projection.png` and `qc/{sample}_projection.json`
  - **With `use_projection` only.** The two channels Cellpose segmented, downsampled, nuclear in
    magenta and cell in green; and the markers in each, their rescaling bounds, the share of
    pixels in which each is the brightest (`win_share`), and the method. `dominant` lists any
    marker brightest in over half of a channel, which then decides that channel alone; the task
    log warns about it too. The projection is removed from the store unless `keep_projection`.
- `qc/{sample}_{method}_qc_images/`
  - The PNGs the report embeds, kept as files so they can be used on their own. Absent when
    `use_qc_images: false`.
- `qc/{slide}_{method}_slide_report.html`
  - **Dearrayed slides only.** One page for the whole slide, from the per-core metrics: cells
    per core against the slide total, the integrity checks rolled up so a check passes only
    when every core passes and the ones that failed are named, mean intensity per channel with
    one column per core, and the slide's stitching and registration QC. The per-core intensity
    table is the comparison a single core's report cannot make: its own page shows a channel
    against its own histogram, which says whether the channel has signal, not whether it has the
    same signal as the rest of the slide. Core
    detail that is only actionable on one core, the crops, the clusters, the per-channel
    histograms and the patch layout, stays in that core's report rather than being repeated.
- `qc/{sample}_comparison.json` and `qc/{sample}_comparison.html`
  - **When both methods segment cells.** Cell counts, median areas (px²), the share of each
    method's cells matched one-to-one at IoU ≥ 0.5, and both outlines on the same three crops
    across the density range. Keys are listed in `bin/compare_segmentations.py`.

</details>

The QC report is produced per sample and method (`cellpose`, `instanseg`), which on a dearrayed
slide means per core and method. `use_qc: false`
skips it entirely; `use_qc_images: false` keeps the metrics and the charts but drops the
clustering and the image crops, which are the slow part. Tuning for the image step — the Leiden
resolution ladder, the arcsinh cofactor, how many crops — goes through `ext.args` for `QC_IMAGES`
in `conf/modules.config` rather than through pipeline parameters.

> [!NOTE]
> Booleans cannot be switched off from the command line, and the pipeline now stops at startup
> rather than doing the opposite of what was asked. `--use_qc false` used to enable QC: Nextflow
> reads the flag on its own, sets it true, and throws the `false` away before any pipeline code
> runs. Set booleans in a params file (`use_qc: false`), which is where a real boolean survives.
> A bare flag still works to switch one on. This applies to every boolean the pipeline has, not
> only these two.

Upstream nf-core/sopa also produced a `{sample}.explorer/` directory holding a Xenium Explorer
bundle and a standalone `adata.h5ad`. **This pipeline does not export to Xenium Explorer.** The
cell tables are inside `{sample}.zarr` under `tables/`, and can be pulled out with
`spatialdata.read_zarr(...).tables`.

### Pipeline information

<details markdown="1">
<summary>Output files</summary>

- `pipeline_info/`
  - From Nextflow: `execution_report_{ts}.html`, `execution_timeline_{ts}.html`,
    `execution_trace_{ts}.txt` and `pipeline_dag_{ts}.html`.
  - `histo_software_versions.yml`, every tool version, and `params_{ts}.json`, the parameters used.
  - `pipeline_report.html` and `.txt`, only when `email` or `email_on_fail` is set.

</details>

[Nextflow](https://www.nextflow.io/docs/latest/tracing.html) provides excellent functionality for generating various reports relevant to the running and execution of the pipeline. This will allow you to troubleshoot errors with the running of the pipeline, and also provide you with other information such as launch commands, run times and resource usage.
