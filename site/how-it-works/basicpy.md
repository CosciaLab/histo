# Illumination correction: BaSiCPy

## The idea

A microscope does not light its field of view evenly. Each tile is brighter in some parts than
others, so a stitched mosaic shows seams, and a cell's measured intensity depends on where in
the tile it sat.

% source: doi:10.1038/ncomms14836

BaSiC models a measured tile as the true image times a **flat-field** (the uneven illumination)
plus a **dark-field** (camera offset and thermal noise). It estimates both from the tiles
themselves, without extra reference images. Stacked together, the tiles split into a low-rank
part, the shading they all share, and a sparse residual, where the tissue and debris that differ
between tiles end up [@doi:10.1038/ncomms14836].

% source: doi:10.1038/ncomms14836

BaSiC needs far fewer images than earlier methods that work from the data alone: it improves
image quality from as few as five, and a whole-slide scan typically has 50–200 tiles. BaSiCPy is
the Python package built on the original BaSiC tool.

% source: doi:10.1038/ncomms14836
% source: https://github.com/peng-lab/BaSiCPy#readme

:::{figure} ../images/how-it-works/basic-fig1.jpg
:alt: A mouse brain mosaic with a grid of seams, the BaSiC decomposition into low-rank and residual matrices, and the corrected mosaic without seams.

(a) A whole-slide mosaic with seams from uneven illumination. (c) The BaSiC workflow: tiles
are decomposed into shared shading and a residual. (d) The corrected mosaic. Panels (b) and (e)
show time-lapse correction, which this pipeline does not use. Reproduced from
[@doi:10.1038/ncomms14836], CC BY 4.0.
:::

## Why this pipeline uses it

Illumination correction is the first step of the preprocessing half, taken from nf-core/mcmicro.
Its profiles go to Ashlar, which applies them while stitching.

% source: docs/decisions.md#architecture
% source: README.md#steps
% source: subworkflows/local/preprocess_images/main.nf:37-52

## In this pipeline

```{include} ../_generated/modules/basicpy.md

```

- One BaSiCPy task per sample and cycle. It fits one profile per channel from that cycle's
  tiles.
- Ashlar receives each sample's profiles in `cycle_number` order, alongside the images.
- The profiles are published under `preprocessing/illumination/`; see
  [output](../reference/output.md#preprocessing).
- `.czi` input is read tile by tile: the pipeline's copy of the BaSiCPy script turns off
  Bio-Formats' automatic stitching, which otherwise leaves BaSiC a single field to fit.

% source: conf/modules.config:15-24
% source: bin/basicpy_main.py:262-275
% source: subworkflows/local/preprocess_images/main.nf:19-52
% source: CHANGELOG.md:421-427

What steers it:

- [`use_preprocessing`](../reference/parameters.md#use_preprocessing): BaSiCPy runs only in the
  preprocessing half.
- The `dfp` and `ffp` columns of the [cycle sheet](../reference/samplesheet.md#cycle-sheet):
  profiles given there are used as they are, and BaSiCPy does not run for that cycle. Give them
  for every cycle of a sample or for none.
- No parameter passes arguments to BaSiCPy.

% source: subworkflows/local/preprocess_images/main.nf:19-35
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:225-237
% source: conf/modules.config:15-24

## Caveats

- **The dark-field is not fitted.** The script's `--darkfield` flag is off by default and the
  pipeline passes no arguments.
- **Structure in the same place in every tile looks like shading.** BaSiC assumes the tissue
  differs from tile to tile; the authors advise checking the estimated profile by eye.
- **No Mac runs.** BaSiCPy needs AVX, which Docker under Rosetta does not offer; see
  [On the Mac](https://github.com/CosciaLab/histo/blob/dev/docs/CONTRIBUTING.md#on-the-mac).
- **No conda.** The module stops under `-profile conda` or `mamba`; use a container.

% source: bin/basicpy_main.py:108-115
% source: conf/modules.config:15-24
% source: doi:10.1038/ncomms14836
% source: docs/CONTRIBUTING.md#on-the-mac
% source: modules/nf-core/basicpy/main.nf:20

## Read more

- The BaSiC paper: [@doi:10.1038/ncomms14836].
- [BaSiCPy documentation](https://basicpy.readthedocs.io/) and
  [source](https://github.com/peng-lab/BaSiCPy).
- The container, from MCMICRO:
  [labsyspharm/basicpy-docker-mcmicro](https://github.com/labsyspharm/basicpy-docker-mcmicro).
