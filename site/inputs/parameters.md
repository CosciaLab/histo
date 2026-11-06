# Parameters

Parameters say what to run. Put them in a `params.yml` file and pass it with `-params-file`:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_instanseg: true
instanseg_pixel_size: 0.65
```

Every run needs `input` (the [samplesheet](samplesheet.md)) and `outdir` (where results go), and
a segmentation method. Everything else has a default. This page covers the parameters most runs
change, by topic; [All parameters](parameters-full.md) lists every one.

Write `true` and `false` in the params file. On the command line, `--use_backsub false` does not
switch it off, so the run refuses it; use the params file for anything that is off.

% source: docs/usage.md#parameters
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:143-147

The run checks combinations when it starts and stops with a message when they do not fit. The
rules are given under each topic below.

## Which steps run

By default the pipeline corrects illumination, stitches, segments, quantifies and writes a QC
report. Two switches change the route:

| You want                             | Set                                                                   | Tutorial                                          |
| ------------------------------------ | --------------------------------------------------------------------- | ------------------------------------------------- |
| Start from images stitched elsewhere | [`use_preprocessing`](parameters-full.md#use_preprocessing)`: false`  | [Pre-stitched image](../tutorials/prestitched.md) |
| Stitched images only, nothing after  | [`preprocessing_only`](parameters-full.md#preprocessing_only)`: true` | [Stitching only](../tutorials/stitching-only.md)  |

Two optional steps add to the route; both need the raw-cycle route:
[background subtraction](#background-subtraction) and [TMA dearray](#tma-dearray).

% source: docs/usage.md#parameters
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:648-704

## Segmentation

### Methods and targets

Pick one method or both. Unless `preprocessing_only`, at least one is needed.

| Method                               | Set                                                                                                                                                          | Channels it reads                                                      |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| [Cellpose](../modules/cellpose.md)   | [`use_cellpose`](parameters-full.md#use_cellpose)`: true` and [`cellpose_channels`](parameters-full.md#cellpose_channels), e.g. `"CD45 DNA_1"`, nuclear last | the two you name, or two [projected](#many-markers-with-cellpose) ones |
| [InstanSeg](../modules/instanseg.md) | [`use_instanseg`](parameters-full.md#use_instanseg)`: true` and [`instanseg_pixel_size`](parameters-full.md#instanseg_pixel_size), your pixel size in µm     | every `dna` and `marker` channel of the marker sheet                   |

Then pick what to find. Cells are on by default.

| You want                            | Set                                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------------------ |
| Cells                               | nothing                                                                              |
| Cells, nuclei and cytoplasm, linked | [`segment_nuclei`](parameters-full.md#segment_nuclei)`: true`                        |
| Nuclei only                         | [`segment_cells`](parameters-full.md#segment_cells)`: false`, `segment_nuclei: true` |

Each method × target is one more pass over the image: two methods and two targets are four.
With both methods finding cells, the QC compares them. How to choose:
[Multiple segmentations](../tutorials/multiple-segmentations.md).

- Cellpose finds nuclei on the last of `cellpose_channels`; InstanSeg on the `dna` channels.
- Pre-stitched images have no marker sheet, so InstanSeg there needs
  [`instanseg_channels`](parameters-full.md#instanseg_channels).
- Cellpose needs `cellpose_channels` or `use_projection`, not both.

% source: docs/usage.md#methods-and-targets
% source: modules/local/utils.nf:57-68
% source: modules/local/utils.nf:196-201
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:642-676

### Many markers with Cellpose

Cellpose looks at two channels, nuclear and cell, but an mIF panel spreads cell outlines across
many markers. [Channel projection](../modules/projection.md) combines them into those two
channels:

```yaml
use_cellpose: true
use_projection: true
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0
```

- [`use_projection`](parameters-full.md#use_projection) builds the nuclear channel from the first
  `dna` channel and the cell channel from every `marker` whose compartment is `membrane` or
  `cytoplasm`. To choose by hand, use the marker sheet's
  [`segmentation` column](markers.md#optional-columns).
- **Keep the three thresholds.** Without them, Cellpose runs with settings that divide the whole
  tissue into cells, whatever the image shows.
- After the run, open `qc/{sample}_projection.png`, what Cellpose saw. If one marker is listed
  under `dominant` in `qc/{sample}_projection.json`, it drowns the others: set its
  `segmentation` to `none` and run again.
- [`keep_projection`](parameters-full.md#keep_projection)`: true` keeps the projected image in
  the store, to view under the outlines.
- Needs the raw-cycle route, because it reads the marker sheet.

% source: docs/usage.md#two-channel-segmentation-use-projection
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:394-427
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-676

### Patch size

The image is cut into square patches that are segmented in parallel; see
[Tiled segmentation](../modules/tiling.md). [`patch_width_pixel`](parameters-full.md#patch_width_pixel)
sets their width. The default, 2000 px, suits TMA cores and small slides. **Set it for anything
larger**: aim for 16 to 200 patches.

| Stitched image (px) | 2000 | 5000 | 8000 | 10000 |
| ------------------- | ---- | ---- | ---- | ----- |
| 3 000 × 3 000       | 4    | 1    | 1    | 1     |
| 25 000 × 25 000     | 169  | 25   | 16   | 9     |
| 50 000 × 50 000     | 625  | 100  | 49   | 25    |
| 115 000 × 115 000   | 3364 | 529  | 225  | 144   |

The rule: `patch_width_pixel = √(width × height / patches)`. A 30 000 × 20 000 px image at 70
patches gives 2928; round to 3000. The image size is in the stitched OME-TIFF's metadata, which
QuPath or Fiji show when you open it.

- One patch means no parallelism; thousands cost more in scheduling than in work.
- InstanSeg's memory grows with patch area × channels: at 3000 px, 0.65 µm/px and 8 channels, a
  patch asks for 39 GB. Above 64 GB the run warns and suggests a width that fits.
- [`patch_overlap_pixel`](parameters-full.md#patch_overlap_pixel) (default 100): about twice a
  cell diameter.
- Keep the width the same when you compare runs; it changes results at patch edges.

% source: docs/usage.md#choosing-patch-width-pixel
% source: modules/local/utils.nf:171-189
% source: subworkflows/local/segmentation/main.nf:56-69
% source: docs/decisions.md#parameters

### GPU

On the cluster, [`use_gpu`](parameters-full.md#use_gpu)`: true` gives each Cellpose and InstanSeg
patch one GPU. Run with the `slurm` profile; with `mdc` as well, it asks for an A40. See
[GPU](../getting-started/usage-guide.md#gpu) for other clusters.

- InstanSeg on a GPU takes at most 10 channels for now. With more in the marker sheet, name 10
  or fewer in [`instanseg_channels`](parameters-full.md#instanseg_channels), e.g.
  `"DNA_1 CD45 PanCK CD3 CD8"`; the run checks at startup.
- A patch without a usable GPU fails; it does not quietly fall back to the CPU.
- Not on a Mac.

% source: docs/usage.md#gpu-segmentation
% source: conf/gpu.config
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:378-389
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:678-683
% source: modules/local/segment_patch/main.nf:19-21

### Skip empty glass

[`use_tissue_segmentation`](parameters-full.md#use_tissue_segmentation)`: true` finds the tissue
first and segments only patches that touch it. For fluorescence, also set `mode: staining`:

```yaml
use_tissue_segmentation: true
mode: staining
```

- It takes the brightest channel at each pixel at low resolution, separates tissue from glass
  automatically (Otsu's method), and drops specks smaller than 1 % of the tissue.
- [`tissue_segmentation_kwargs`](parameters-full.md#tissue_segmentation_kwargs) steers it, written
  with double quotes: `'{"channel": "DNA_1", "drop_threshold": 0.001}'` uses one channel and keeps
  smaller pieces. [`level`](parameters-full.md#level) picks the resolution it reads.
- **Without `mode`, an image with exactly three channels** is treated as H&E (`saturation`
  mode), which expects an 8-bit colour image.
- If no tissue is found, nothing is segmented and the run stops, naming the sample.
- Check the outline, `region_of_interest`, over the image in a [viewer](../outputs/reports.md#viewers).

% source: nextflow_schema.json:269-286
% source: modules/local/utils.nf:4-47
% source: https://github.com/prism-oncology/sopa/blob/v2.2.9/sopa/segmentation/_tissue.py#L72-L230
% source: subworkflows/local/segmentation/main.nf:34-40

## Preprocessing

### Stitching

[Ashlar](../modules/ashlar.md) stitches and aligns the cycles. Its settings go in
[`ashlar_args`](parameters-full.md#ashlar_args), default `--maximum-shift 30`. Setting it replaces
the default, so repeat what you want to keep:

```yaml
ashlar_args: "--maximum-shift 50 --filter-sigma 1"
```

What to change when: [When stitching looks wrong](../modules/ashlar.md#when-stitching-looks-wrong).
A poor alignment does not stop the run; check the QC report every time.

% source: nextflow_schema.json:65-70
% source: docs/usage.md#when-stitching-or-registration-looks-wrong

### Background subtraction

[`use_backsub`](parameters-full.md#use_backsub)`: true` subtracts autofluorescence channels from
the markers before segmentation; see [backsub](../modules/backsub.md). The marker sheet needs
[`exposure` and `background` columns](markers.md#background-subtraction-columns). Tutorial:
[WSI with background subtraction](../tutorials/wsi-backsub.md).

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:327-363

### TMA dearray

[`use_tma_dearray`](parameters-full.md#use_tma_dearray)`: true` cuts a tissue microarray into
cores, processes each core alone and merges them per slide; see
[Coreograph](../modules/coreograph.md). It needs:

- [`tma_expected_cores`](parameters-full.md#tma_expected_cores): how many cores the slide has (a
  count, not rows × columns), and
- [`tma_core_diameter_mm`](parameters-full.md#tma_core_diameter_mm): their diameter in mm.

From these the pipeline tries several detection settings and keeps the one that finds the cores
you expect. Both apply to every slide in the run, so run arrays with different layouts
separately. To set Coreograph yourself instead, use
[`coreograph_args`](parameters-full.md#coreograph_args). Tutorial: [TMA](../tutorials/tma.md).

% source: docs/usage.md#tma-dearray
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:695-704

## Quality control

On by default. [`use_qc`](parameters-full.md#use_qc) writes the QC report and Ashlar's stitching
QC; [`use_qc_images`](parameters-full.md#use_qc_images) adds outline crops and a clustering of
cells to the report, which takes minutes rather than seconds. To switch either off, write
`false` in the params file. What the report shows: [Reports](../outputs/reports.md#the-qc-report).

% source: nextflow_schema.json:474-494
% source: docs/output.md#qc-report
