# Stitching and registration: Ashlar

## The idea

A cyclic immunofluorescence slide is scanned as overlapping tiles, once per staining cycle.
ASHLAR turns them into one image in three phases: it stitches the tiles of the first cycle,
registers every later cycle's tiles to the first cycle, and writes one many-channel mosaic. Only
one reference channel, usually the nuclear stain, is used to align.

% source: doi:10.1093/bioinformatics/btac544

**Stitching.** Neighbouring tiles are found from the recorded stage positions and aligned on
their overlap by phase correlation. Phase correlation returns a shift even for an empty
overlap, so ASHLAR sets an error threshold from 1000 pairs of non-adjacent tiles and discards
alignments above it, or shifted further than a user limit. A minimum spanning tree over the
remaining pairs fixes one position per tile. Discarding pairs can split the mosaic into pieces;
a linear model of corrected against recorded stage positions places them
[@doi:10.1093/bioinformatics/btac544].

% source: doi:10.1093/bioinformatics/btac544

**Registration.** Each later cycle is first aligned coarsely on downsampled thumbnails, then
tile by tile against the nearest first-cycle tile, again filtered by the shift limit. Tiles that
fail, usually in empty or damaged regions, are placed by the linear model. Every cycle is
registered to the first, not to the one before, so errors do not add up.

% source: doi:10.1093/bioinformatics/btac544

:::{figure} ../images/how-it-works/ashlar-fig2.jpg
:alt: Three columns of schematic steps: stitching (A1 to A5), registration (B1 to B5) and mosaic generation.

ASHLAR's phases. (a) Stitching within one cycle. (b) Registration across cycles. (c) Mosaic
generation. Reproduced from [@doi:10.1093/bioinformatics/btac544], CC BY 4.0.
:::

## Why this pipeline uses it

Stitching and registration come from nf-core/mcmicro, with the preprocessing half. Ashlar runs
from the pipeline's own public image, `josenimo/ashlar`: it is the only way to get rotation
correction between cycles, alignment of each cycle on its own last channel, and
machine-readable stitching QC. None of these is in a bioconda release.

% source: docs/decisions.md#architecture
% source: docs/decisions.md#containers

## In this pipeline

```{include} ../_generated/modules/ashlar.md

```

- One Ashlar task per sample, with all its cycles in `cycle_number` order and the BaSiCPy
  profiles.
- The stitched `preprocessing/registration/{sample}.ome.tif` is the handoff to the SpatialData
  half; see [output](../reference/output.md#preprocessing).
- With `use_qc`, Ashlar also writes its own QC, which the QC report shows as "Stitching and
  registration". [What to try when it looks wrong](../reference/usage.md#when-stitching-or-registration-looks-wrong).
- Ashlar writes no marker names; they are added to the Zarr later. The pixel size stays in the
  OME-TIFF.

% source: subworkflows/local/preprocess_images/main.nf:37-52
% source: conf/modules.config:26-35
% source: docs/output.md#preprocessing
% source: docs/decisions.md#channel-names
% source: docs/decisions.md#pixel-size

What steers it:

- [`ashlar_args`](../reference/parameters.md#ashlar_args), default `--maximum-shift 30`: passed
  through to Ashlar. `-c` picks the alignment channel.
- [`use_qc`](../reference/parameters.md#use_qc): adds Ashlar's QC output and PDF report.
- [`skip_reference_dna_check`](../reference/parameters.md#skip_reference_dna_check): run even
  when the alignment channel is not `dna`.
- [`use_preprocessing`](../reference/parameters.md#use_preprocessing) and
  [`preprocessing_only`](../reference/parameters.md#preprocessing_only).

% source: nextflow_schema.json (preprocessing group)
% source: conf/modules.config:26-35

## Caveats

- **The alignment channel must be `dna` in every cycle.** `-c` is an index within each cycle;
  if it lands on a non-`dna` channel in any cycle, the run stops at startup.
- **A poor alignment does not stop the run.** Tiles whose alignment was rejected are placed by
  the stage model, and the mosaic is written anyway. Check the QC report section.
- **One job per slide.** On a TMA, Ashlar registers the whole slide (about 1000 tiles × 7
  cycles) before dearraying, so one failure loses every core.
- **No conda.** The fork is not on bioconda; use Singularity, Apptainer or Docker.

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-500
% source: doi:10.1093/bioinformatics/btac544
% source: ROADMAP.md#separate-track-dearray-before-ashlar
% source: CHANGELOG.md:218-219

## Read more

- The ASHLAR paper: [@doi:10.1093/bioinformatics/btac544].
- [ASHLAR documentation](https://labsyspharm.github.io/ashlar/).
- The fork this pipeline runs: [josenimo/ashlar](https://github.com/josenimo/ashlar), branch
  `histo-qc`.
