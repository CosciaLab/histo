# Marker sheet

The marker sheet says what each channel of the stitched image is. One row per channel, across
all cycles. Only raw-cycle runs use it; a pre-stitched image takes its channel names from the
image itself.

% source: docs/usage.md#inputs
% source: assets/schema_marker.json

## Example

Two cycles of four channels, each cycle starting with its nuclear stain:

| channel_number | cycle_number | marker_name | channel_role | channel_compartment | filter |
| -------------- | ------------ | ----------- | ------------ | ------------------- | ------ |
| 1              | 1            | DNA_1       | dna          | nuclear             | DAPI   |
| 2              | 1            | CD45        | marker       | membrane            | FITC   |
| 3              | 1            | PanCK       | marker       | cytoplasm           | Cy3    |
| 4              | 1            | CD3         | marker       | membrane            | Cy5    |
| 5              | 2            | DNA_2       | dna          | nuclear             | DAPI   |
| 6              | 2            | CD8         | marker       | membrane            | FITC   |
| 7              | 2            | CD68        | marker       | cytoplasm           | Cy3    |
| 8              | 2            | Ki67        | marker       | nuclear             | Cy5    |

:::{dropdown} As CSV, to copy

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter
1,1,DNA_1,dna,nuclear,DAPI
2,1,CD45,marker,membrane,FITC
3,1,PanCK,marker,cytoplasm,Cy3
4,1,CD3,marker,membrane,Cy5
5,2,DNA_2,dna,nuclear,DAPI
6,2,CD8,marker,membrane,FITC
7,2,CD68,marker,cytoplasm,Cy3
8,2,Ki67,marker,nuclear,Cy5
```

:::

% source: site/tutorials/multiple-segmentations.md (before restructure: vignettes/mif-slide.md)

## The required columns

- **`channel_number`** counts 1, 2, 3, … across all cycles. It does not restart at each cycle.
- **`cycle_number`** is the cycle the channel was acquired in, as in the samplesheet.
- **`marker_name`** is the name you want in your results: it becomes the channel name in the
  image and the column name in the cell table. Each name once only.
- **`channel_role`** says what the pipeline should do with the channel:

| Role               | Meaning                                                                                             |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| `dna`              | A nuclear stain, such as DAPI or Hoechst. Every cycle needs at least one.                           |
| `marker`           | A biological readout, such as CD3.                                                                  |
| `autofluorescence` | A channel acquired only to be subtracted from others; see [below](#background-subtraction-columns). |
| `blank`            | A channel expected to be dark. QC checks that it is.                                                |

The nuclear stain is read by stitching, segmentation and the QC check for cells lost between
cycles. Naming the role, rather than guessing from the name, means a Hoechst stain is found as
surely as a DAPI one.

% source: assets/schema_marker.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:289-316

## Where the nuclear stain sits

[Ashlar](../modules/ashlar.md) lines up every cycle on the **same position within the cycle**:
by default, the first channel of each cycle. That channel must be a `dna` channel in every cycle,
or the run stops at startup. So put the nuclear stain first in each cycle, as in the example.

If your nuclear stain is elsewhere, tell Ashlar its position with `-c` in
[`ashlar_args`](parameters-full.md#ashlar_args) (counting from 0; `-1` is the last). For a TMA,
[Coreograph](../modules/coreograph.md) finds cores on the first `dna` channel. To run anyway on a
channel that is not `dna`, set [`skip_reference_dna_check`](parameters-full.md#skip_reference_dna_check).

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-500

## Optional columns

- **`channel_compartment`**: where in the cell the signal belongs: `nuclear`, `cytoplasm`,
  `membrane`, or a combination joined with `+`, such as `nuclear+cytoplasm`. QC uses it to check
  that a marker landed where it should, and [channel projection](../modules/projection.md) uses it
  to pick Cellpose's cell channel. Blank costs a check, not a run.
- **`segmentation`**: only with [`use_projection`](parameters-full.md#use_projection). Which of
  Cellpose's two channels a marker feeds: `nuclear`, `cell` or `none`. Without the column, the
  first `dna` channel is `nuclear`, and every `marker` whose compartment includes `membrane` or
  `cytoplasm` is `cell`. Once any row has a value, the column is the whole selection: blank rows
  are left out, the `dna` channel included. See [Many markers with Cellpose](parameters.md#many-markers-with-cellpose).
- **`filter`**, **`excitation_wavelength`**, **`emission_wavelength`**: for your records.

% source: assets/schema_marker.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:394-427
% source: bin/qc_metrics.py:320-322

## Background subtraction columns

Only with [`use_backsub`](parameters-full.md#use_backsub), which subtracts autofluorescence
channels from the markers; see [backsub](../modules/backsub.md).

- **`exposure`**: every channel needs one. Backsub scales the background by the ratio of
  exposure times.
- **`background`**: on a marker, the `marker_name` of the channel to subtract from it. That channel
  must have the role `autofluorescence`.
- **`remove`**: `true` drops the channel after subtraction, typically the autofluorescence
  channels. Keep at least one `dna` channel, and do not name a removed channel in
  `cellpose_channels` or `instanseg_channels`. Without `use_backsub`, `remove` is ignored with a
  warning.

| channel_number | cycle_number | marker_name | channel_role     | channel_compartment | exposure | background | remove |
| -------------- | ------------ | ----------- | ---------------- | ------------------- | -------- | ---------- | ------ |
| 1              | 1            | DNA_1       | dna              | nuclear             | 20       |            |        |
| 2              | 1            | AF_FITC     | autofluorescence |                     | 100      |            | true   |
| 3              | 2            | DNA_2       | dna              | nuclear             | 20       |            |        |
| 4              | 2            | CD45        | marker           | membrane            | 100      | AF_FITC    |        |

:::{dropdown} As CSV, to copy

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,exposure,background,remove
1,1,DNA_1,dna,nuclear,20,,
2,1,AF_FITC,autofluorescence,,100,,true
3,2,DNA_2,dna,nuclear,20,,
4,2,CD45,marker,membrane,100,AF_FITC,
```

:::

A full run with these columns: [WSI with background subtraction](../tutorials/wsi-backsub.md).

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:316-371
% source: site/tutorials/wsi-backsub.md

## Before a long run

The run checks the sheet when it starts: numbering, unique names, a `dna` channel per cycle, the
nuclear stain's position, and the backsub and projection columns. It stops with a message naming
the sample and the problem. One check comes later: that the sheet lists as many channels as the
stitched image has, which is known only after stitching.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:289-500
% source: bin/set_channel_names.py:94-102

## Columns

Generated from the schema the run validates against.

```{include} ../_generated/sheets/marker.md

```
