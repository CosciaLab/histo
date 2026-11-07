# Step-by-step guide

From raw images to a table of cells, on a computing cluster. About ten minutes to read. You type
a handful of commands; no programming. Every step links to the page with the details.

## 1. Get set up

You need three things on the cluster, once:

1. **Nextflow**, version 25.10.4 or later. Follow its
   [installation guide](https://www.nextflow.io/docs/latest/install.html); it is one command.
2. **The software images** the pipeline runs in. The pipeline downloads nothing while it runs, so
   these must be in place first. Ask whoever maintains the pipeline at your site where they are,
   and set the folder in your environment, for example in `~/.bashrc`:

   ```bash
   export NXF_SINGULARITY_CACHEDIR=/path/your/admin/gave/you
   ```

3. **A working folder** with space for the results, separate from where your raw images are.

% source: nextflow.config:320
% source: docs/usage.md#fetching-images
% source: docs/usage.md#staging-images-into-the-shared-cache

At the MDC, the [dropbox](../mdc.md) can run the pipeline for you instead.

## 2. Find your images

Note the full path of each cycle's image file, for example
`/data/myproject/raw/slide01/cycle01.ome.tiff`. Any format the microscope software writes and
Bio-Formats reads works, one file per cycle. Use full paths, starting with `/`, and no spaces.

% source: README.md:3-4
% source: docs/usage.md#inputs

## 3. Write the samplesheet

The samplesheet lists your images: one row per cycle. Write it in a spreadsheet and save it as
CSV (comma-separated), for example `samplesheet.csv`.

| sample  | cycle_number | image_tiles                                  | marker_sheet                               |
| ------- | ------------ | -------------------------------------------- | ------------------------------------------ |
| slide01 | 1            | /data/myproject/raw/slide01/cycle01.ome.tiff | /data/myproject/sheets/markers_slide01.csv |
| slide01 | 2            | /data/myproject/raw/slide01/cycle02.ome.tiff | /data/myproject/sheets/markers_slide01.csv |

- `sample`: a short name for the slide, used in every output file name.
- `cycle_number`: 1, 2, 3, … with no gaps.
- `marker_sheet`: the sheet you write in the next step, the same on every row of a sample.

:::{dropdown} The same samplesheet as CSV

```text
sample,cycle_number,image_tiles,marker_sheet
slide01,1,/data/myproject/raw/slide01/cycle01.ome.tiff,/data/myproject/sheets/markers_slide01.csv
slide01,2,/data/myproject/raw/slide01/cycle02.ome.tiff,/data/myproject/sheets/markers_slide01.csv
```

:::

All columns and rules: [Samplesheet](../inputs/samplesheet.md).

% source: assets/schema_input_cycle.json
% source: docs/usage.md#inputs

## 4. Write the marker sheet

The marker sheet names every channel: one row per channel, across all cycles, numbered 1 to N.

| channel_number | cycle_number | marker_name | channel_role | channel_compartment |
| -------------- | ------------ | ----------- | ------------ | ------------------- |
| 1              | 1            | DNA_1       | dna          | nuclear             |
| 2              | 1            | CD45        | marker       | membrane            |
| 3              | 1            | PanCK       | marker       | cytoplasm           |
| 4              | 2            | DNA_2       | dna          | nuclear             |
| 5              | 2            | CD3         | marker       | membrane            |
| 6              | 2            | Ki67        | marker       | nuclear             |

- `marker_name`: what you want to see in the results. Unique.
- `channel_role`: `dna` for the nuclear stain, `marker` for an antibody. Every cycle needs a
  `dna` channel, and it should come first in each cycle.
- `channel_compartment`: where the marker sits in the cell. Optional, but it lets the QC check
  that a marker landed where it should.

:::{dropdown} The same marker sheet as CSV

```text
channel_number,cycle_number,marker_name,channel_role,channel_compartment
1,1,DNA_1,dna,nuclear
2,1,CD45,marker,membrane
3,1,PanCK,marker,cytoplasm
4,2,DNA_2,dna,nuclear
5,2,CD3,marker,membrane
6,2,Ki67,marker,nuclear
```

:::

All columns and rules: [Marker sheet](../inputs/markers.md).

% source: assets/schema_marker.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-475

## 5. Write the settings file

The settings go in a small text file, `params.yml`. This one segments cells with InstanSeg, which
reads every marker and needs only the pixel size of your images in µm:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_instanseg: true
instanseg_pixel_size: 0.65
```

- `input`: the samplesheet from step 3.
- `outdir`: where the results go. The folder is created for you.
- For a slide larger than a few mm, also set `patch_width_pixel`; see
  [patch size](../inputs/parameters.md#patch-size).

Other choices, such as Cellpose instead, nuclei as well as cells, or a TMA:
[Parameters](../inputs/parameters.md).

% source: docs/usage.md#parameters
% source: docs/usage.md#choosing-patch-width-pixel
% source: modules/local/utils.nf:196-201

## 6. Start the run

On the cluster's login node, go to your working folder and start a `tmux` session, so the run
keeps going when you log out:

```bash
cd /path/to/my/working/folder
tmux new -s histo
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

What each part means:

- `nextflow run CosciaLab/histo`: run this pipeline.
- `-r v2.0.0`: this version of it, so a rerun next year gives the same result.
- `-profile singularity,size_small,slurm`: run the software in Singularity containers, ask for
  resources sized for images up to about 50 GB, and send each step to the cluster's queue. See
  [Profiles](usage-guide.md#profiles); at the MDC add `mdc`.
- `-params-file params.yml`: your settings from step 5.

Leave tmux with `Ctrl-b` then `d`; come back with `tmux attach -t histo`. The cluster setup in
full: [Running on the cluster](usage-guide.md#running-on-the-cluster).

% source: docs/usage.md#quick-start
% source: docs/usage.md#profiles
% source: docs/usage.md#running-on-the-cluster

## 7. Watch it run

Nextflow prints one line per step, with how many tasks are done. A large slide can take many
hours, much of it waiting in the cluster queue. When it finishes it prints
`Pipeline completed successfully`.

% source: subworkflows/nf-core/utils_nfcore_pipeline/main.nf:346

Nextflow keeps its working files in a `work/` folder inside your working folder. Leave it there
until you are happy with the results: it is what lets you resume.

% source: https://www.nextflow.io/docs/latest/cache-and-resume.html

## If something fails

1. **Read the error Nextflow prints.** It names the step that failed and its work folder, a path
   under `work/`.
2. **Open that folder** and read `.command.err`: the step's own error message. `.command.out`
   holds its normal output, and `.command.sh` the exact command that ran.
3. **If the run stopped before any step started**, the problem is in your sheets or settings. The
   message names the sample, the sheet and the column. `.nextflow.log` in your working folder has
   the full story.
4. **Fix the cause, and run the same command again with `-resume` added.** Steps that already
   finished are reused, so only the failed part runs again.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:143-162
% source: https://www.nextflow.io/docs/latest/cache-and-resume.html
% source: Nextflow 26.10.4, a failing task run on 2026-11-05: the files listed and their contents

Keep `work/` and the hidden `.nextflow/` folder in your working folder: `-resume` needs both.
More on resuming: [Resume a run](usage-guide.md#resume-a-run). Problems visible only in the results,
such as missing cells: [Common failures](../outputs/reports.md#common-failures).

% source: docs/usage.md#id-resume-and-the-store

## Look at the results

A finished run is not yet a run that worked: the pipeline never fails on bad quality. Look, in
this order:

1. **The QC report**, `qc/{sample}_instanseg_qc_report.html`. Open it in any browser. Start with
   "Stitching and registration", then the segmentation overlay. What each section means:
   [Reports](../outputs/reports.md#the-qc-report).
2. **The stitched image**, `preprocessing/registration/{sample}.ome.tif`, in QuPath or napari.
3. **The cells over the image**, in the store `{sample}.zarr`. See
   [viewers](../outputs/reports.md#viewers).

Every file, one by one: [Outputs](../outputs/outputs.md).

% source: docs/output.md#qc-report
% source: docs/output.md#preprocessing
% source: docs/output.md#spatialdata-directory

## Open the results in Python

Everything for one sample is in `{sample}.zarr`. To work with it, install
[spatialdata](https://spatialdata.scverse.org/en/stable/) (`pip install spatialdata`) and read it:

```python
import spatialdata as sd

sdata = sd.read_zarr("results/slide01.zarr")
print(sdata)  # every image, outline set and table

adata = sdata.tables["instanseg_table"]  # one row per cell
cells = sdata.shapes["instanseg_cells"]  # outlines, with the same cell ids

means = adata[:, adata.var["statistic"] == "mean"].to_df()  # cells × {marker}_mean
adata.obs[["cell_area", "slide"]]                           # area in pixels²
```

`adata` is an [AnnData](https://anndata.readthedocs.io) table, ready for scanpy or squidpy. With
Cellpose, the names start with `cellpose_`. Table names for other runs, and what NaN means in the
table: [The store](../outputs/zarr.md).

% source: docs/output.md#spatialdata-directory
% source: bin/aggregate_compartments.py:199-260
% source: snippet run on 2026-11-05 with spatialdata 0.8.0 against a store built with build_table
