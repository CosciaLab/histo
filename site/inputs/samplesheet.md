# Samplesheet

The samplesheet tells the pipeline where your images are. It has one of two shapes, depending on
whether the pipeline should stitch the images ([`use_preprocessing`](parameters-full.md#use_preprocessing),
on by default) or they are stitched already.

% source: nextflow_schema.json (input)
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:124-146

## Cycle sheet

For raw images: **one row per acquisition cycle**. Rows with the same `sample` are one slide;
the pipeline stitches its cycles together into one image.

| sample  | cycle_number | image_tiles                                  | marker_sheet                               |
| ------- | ------------ | -------------------------------------------- | ------------------------------------------ |
| slide01 | 1            | /data/myproject/raw/slide01/cycle01.ome.tiff | /data/myproject/sheets/markers_slide01.csv |
| slide01 | 2            | /data/myproject/raw/slide01/cycle02.ome.tiff | /data/myproject/sheets/markers_slide01.csv |
| slide02 | 1            | /data/myproject/raw/slide02/cycle01.ome.tiff | /data/myproject/sheets/markers_slide02.csv |

:::{dropdown} As CSV, to copy

```csv
sample,cycle_number,image_tiles,marker_sheet
slide01,1,/data/myproject/raw/slide01/cycle01.ome.tiff,/data/myproject/sheets/markers_slide01.csv
slide01,2,/data/myproject/raw/slide01/cycle02.ome.tiff,/data/myproject/sheets/markers_slide01.csv
slide02,1,/data/myproject/raw/slide02/cycle01.ome.tiff,/data/myproject/sheets/markers_slide02.csv
```

:::

- **`sample`** names the slide and every output file made from it. Letters, digits, `.`, `_` and
  `-` only.
- **`cycle_number`** runs 1, 2, 3, … for each sample, with no gaps or repeats. It sets the order
  in which cycles are stitched, and must match the cycle numbers in the marker sheet.
- **`image_tiles`** is the raw image of that cycle: one file holding all its tiles, or a folder of
  tiles.
- **`marker_sheet`** is the [marker sheet](markers.md) for the sample. Repeat the same file on
  every row of a sample: it describes the whole stitched image, not one cycle. Two samples may
  use different sheets, so one run can mix panels.
- **`dfp`** and **`ffp`**, optional: illumination profiles from an earlier run; see
  [below](#reuse-illumination-profiles).

% source: assets/schema_input_cycle.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:241-287

## Stitched-image sheet

For images stitched elsewhere, with [`use_preprocessing: false`](parameters-full.md#use_preprocessing):
**one row per image**, and no marker sheet.

| sample | data_path                               |
| ------ | --------------------------------------- |
| slideA | /data/myproject/stitched/slideA.ome.tif |
| slideB | /data/myproject/stitched/slideB.ome.tif |

:::{dropdown} As CSV, to copy

```csv
sample,data_path
slideA,/data/myproject/stitched/slideA.ome.tif
slideB,/data/myproject/stitched/slideB.ome.tif
```

:::

- **`data_path`** is the stitched OME-TIFF, the only format read here.
- **`sample`** is optional; without it, the file name is used.
- Channel names come from the image itself. An image without names gets `Channel:0:0`, … ; see
  the [Pre-stitched image](../tutorials/prestitched.md) tutorial.

% source: assets/schema_input.json
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:124-140
% source: site/tutorials/prestitched.md

## Path rules

- Use **absolute paths**, starting with `/`. A relative path is read from wherever the run is
  launched, which is easy to get wrong.
- **No spaces** in any path or sample name. The run stops at startup if there are.
- Every file must exist when the run starts; it checks.

% source: assets/schema_input_cycle.json (pattern ^\S+$, exists)
% source: docs/usage.md:108
% source: tools/fetch_exemplars.sh:25-29 (paths resolve against the launch directory)

## Reuse illumination profiles

The first step, [BaSiCPy](../modules/basicpy.md), computes an illumination profile per cycle. To
reuse profiles from an earlier run instead of computing them again, give them in two extra
columns. Within one run folder, [resuming](../getting-started/usage-guide.md#resume-a-run) already
reuses them; this is for a new run.

1. Find the earlier run's profiles: `preprocessing/illumination/{sample}_cycle{n}-dfp.ome.tif`
   and `-ffp.ome.tif`, one pair per cycle.
2. Add `dfp` and `ffp` columns to the samplesheet, on **every** cycle row of the sample:

   | sample  | cycle_number | image_tiles                        | dfp                                                              | ffp                                                              | marker_sheet                     |
   | ------- | ------------ | ---------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------- | -------------------------------- |
   | slide01 | 1            | /data/raw/slide01/cycle01.ome.tiff | /data/run1/preprocessing/illumination/slide01_cycle1-dfp.ome.tif | /data/run1/preprocessing/illumination/slide01_cycle1-ffp.ome.tif | /data/sheets/markers_slide01.csv |
   | slide01 | 2            | /data/raw/slide01/cycle02.ome.tiff | /data/run1/preprocessing/illumination/slide01_cycle2-dfp.ome.tif | /data/run1/preprocessing/illumination/slide01_cycle2-ffp.ome.tif | /data/sheets/markers_slide01.csv |

3. Run. BaSiCPy is skipped for those cycles.

Two rules:

- **Every cycle of a sample, or none.** A sample with profiles on only some cycles stops at
  startup, because the profiles would end up matched to the wrong images.
- **Same channels, same order.** A profile holds one plane per channel of its cycle; reuse it
  only for a cycle acquired with the same channels in the same order.

% source: docs/output.md#preprocessing
% source: bin/basicpy_main.py:322-335
% source: subworkflows/local/preprocess_images/main.nf:19-35
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:225-237

## Columns

Generated from the schemas the run validates against.

```{include} ../_generated/sheets/cycle.md

```

```{include} ../_generated/sheets/stitched.md

```
