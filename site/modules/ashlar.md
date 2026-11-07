# Ashlar: stitching and registration

## What it does

A slide is scanned as overlapping tiles, once per staining cycle. Ashlar places the tiles into one
mosaic and aligns every cycle onto the first, so each cell sits at the same pixel in every
channel.

% source: doi:10.1093/bioinformatics/btac544

## Parameters

- [`ashlar_args`](../inputs/parameters-full.md#ashlar_args), default `--maximum-shift 30`: options
  handed to Ashlar as written. The most useful are `--maximum-shift` (how far, in µm, a tile may
  move from its recorded stage position) and `-c` (which channel of each cycle to align on; `0`,
  the first, by default). Setting it replaces the default, so repeat `--maximum-shift` if you
  want to keep it.
- [`use_qc`](../inputs/parameters-full.md#use_qc): also write Ashlar's quality report.
- [`skip_reference_dna_check`](../inputs/parameters-full.md#skip_reference_dna_check): run even
  when the alignment channel is not a nuclear stain (`dna` in the marker sheet).
- [`preprocessing_only`](../inputs/parameters-full.md#preprocessing_only): stop after stitching.

% source: nextflow_schema.json:47-71
% source: nextflow_schema.json:480-485
% source: conf/modules.config:26-35
% source: https://labsyspharm.github.io/ashlar/ (--maximum-shift in micrometers)

## How it works

Ashlar works in three phases, using one reference channel, usually the nuclear stain.

% source: doi:10.1093/bioinformatics/btac544

**Stitching.** Neighbouring tiles are found from the recorded stage positions and aligned on
their overlap by phase correlation. Phase correlation returns a shift even for an empty overlap,
so Ashlar sets an error threshold from 1000 pairs of non-adjacent tiles and discards alignments
above it, or shifted further than `--maximum-shift`. A minimum spanning tree over the remaining
pairs fixes one position per tile. Discarding pairs can split the mosaic into pieces; a linear
model of corrected against recorded stage positions places them
[@doi:10.1093/bioinformatics/btac544].

**Registration.** Each later cycle is first aligned coarsely on downsampled thumbnails, then tile
by tile against the nearest first-cycle tile. Tiles that fail, usually in empty or damaged
regions, are placed by the linear model. Every cycle is registered to the first, not to the one
before, so errors do not add up.

**Mosaic.** All cycles are written as one many-channel image.

% source: doi:10.1093/bioinformatics/btac544

:::{figure} ../images/modules/ashlar-fig2.jpg
:alt: Three columns of schematic steps: stitching (A1 to A5), registration (B1 to B5) and mosaic generation.

Ashlar's phases. (a) Stitching within one cycle. (b) Registration across cycles. (c) Mosaic
generation. Reproduced from [@doi:10.1093/bioinformatics/btac544], CC BY 4.0.
:::

A poor alignment does not stop the run: rejected tiles are placed by the stage model and the
mosaic is written anyway. Check the report every time.

% source: doi:10.1093/bioinformatics/btac544
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-500

**Inputs and outputs.** In: all cycles of one sample (OME-TIFF or other Bio-Formats tile files),
in `cycle_number` order, with their [BaSiCPy](basicpy.md) profiles. Out: one pyramidal OME-TIFF,
`preprocessing/registration/{sample}.ome.tif`, with every channel of every cycle; and, with
`use_qc`, the folder `{sample}_ashlar_qc/`. The OME-TIFF keeps the pixel size but has no marker
names; those are added later, in the [SpatialData store](spatialdata.md). See
[Preprocessing outputs](../outputs/preprocessing.md).

% source: subworkflows/local/preprocess_images/main.nf:37-52
% source: docs/output.md#preprocessing
% source: docs/decisions.md#channel-names
% source: docs/decisions.md#pixel-size

## When stitching looks wrong

Open the "Stitching and registration" section of the [QC report](../outputs/reports.md#the-qc-report)
(the slide report on a TMA), then `preprocessing/registration/{sample}_ashlar_qc/`: the PDF report
with per-tile maps, and `overlay_cycleN.jpg`, cycle 1 in magenta over a later cycle in green.

| What you see                                     | Likely cause                                               | Try in `ashlar_args`                                          |
| ------------------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------- |
| Rejected pairs or several pieces inside tissue   | Stage error larger than `--maximum-shift`, or a weak stain | Raise `--maximum-shift`; check `-c` is a bright nuclear stain |
| Pair errors overlap the random-strip errors      | The alignment channel has little structure                 | A different `-c`; `--filter-sigma 1` for noisy images         |
| One cycle with many tiles far from the model     | Tissue moved or deformed in that cycle                     | Raise `--maximum-shift`; look at that cycle's overlay         |
| Kept tiles no better than chance                 | Alignment locked onto noise in background tiles            | Usually harmless at the tissue edge; check the overlay        |
| Doubled nuclei everywhere in one cycle's overlay | The coarse offset or rotation of that cycle failed         | Check that cycle's dashed outline in the Ashlar PDF           |

% source: docs/usage.md#when-stitching-or-registration-looks-wrong

To try a change quickly:

1. Set `ashlar_args` in your `params.yml`, repeating what you want to keep:
   `ashlar_args: "--maximum-shift 50 --filter-sigma 1"`.
2. Add `preprocessing_only: true`, so the run stops after stitching.
3. Run again from the same folder with `-resume`: illumination correction is reused and only
   Ashlar runs again. Check the PDF and overlays.
4. When it looks right, remove `preprocessing_only` and run again with `-resume`; the stitched
   image is reused.

Keep `-c` on a `dna` channel in every cycle, or the run stops at startup. Do not pass
`--qc-output` or `--report`: the pipeline adds them.

% source: site/how-to/fix-stitching.md (removed)
% source: workflows/histo.nf:66-67
% source: nextflow_schema.json:65-70
% source: https://www.nextflow.io/docs/latest/cache-and-resume.html

## Similar tools

- **MIST** stitches tiles by phase correlation and a stage model
  ([Chalfoun et al. 2017](https://doi.org/10.1038/s41598-017-04567-y)).
- **Fiji Grid/Collection stitching**
  ([Preibisch et al. 2009](https://doi.org/10.1093/bioinformatics/btp184)) and **BigStitcher**
  ([Hörl et al. 2019](https://doi.org/10.1038/s41592-019-0501-0)), interactive tools in Fiji.

These stitch one acquisition; Ashlar also registers the cycles to each other in the same step.
Ashlar came with the preprocessing half from nf-core/mcmicro. The pipeline runs its own build,
`josenimo/ashlar`: the only way to get rotation correction between cycles, alignment of each
cycle on its own last channel, and the machine-readable quality report.

% source: doi:10.1093/bioinformatics/btac544
% source: docs/decisions.md#architecture
% source: docs/decisions.md#containers

## Read more

- The Ashlar paper: [@doi:10.1093/bioinformatics/btac544].
- [Ashlar documentation](https://labsyspharm.github.io/ashlar/).
- The build this pipeline runs: [josenimo/ashlar](https://github.com/josenimo/ashlar), branch
  `histo-qc`.

Version used:

```{include} ../_generated/modules/ashlar.md

```
