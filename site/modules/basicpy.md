# BaSiCPy: illumination correction

## What it does

A microscope does not light its field of view evenly. BaSiCPy calculates, for every channel of
every cycle, a flat-field image of that unevenness, so stitching can correct each tile before it
is placed in the mosaic.

% source: doi:10.1038/ncomms14836
% source: subworkflows/local/preprocess_images/main.nf:37-52

## Parameters

BaSiCPy has no parameters of its own in this pipeline. Two things decide whether it runs:

- [`use_preprocessing`](../inputs/parameters-full.md#use_preprocessing): BaSiCPy runs only when the
  pipeline starts from raw cycles.
- The `dfp` and `ffp` columns of the [samplesheet](../inputs/samplesheet.md): profiles from an
  earlier run are used as they are, and BaSiCPy does not run for those cycles. Give them for every
  cycle of a sample or for none.

% source: subworkflows/local/preprocess_images/main.nf:19-35
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:225-237
% source: conf/modules.config:15-24

## How it works

Without correction, each tile is brighter in some parts than others, so a stitched mosaic shows
seams, and a cell's measured intensity depends on where in the tile it sat.

BaSiC models a measured tile as the true image times a **flat-field** (the uneven illumination)
plus a **dark-field** (camera offset and thermal noise). It estimates both from the tiles
themselves, without extra reference images. Stacked together, the tiles split into a low-rank
part, the shading they all share, and a sparse residual, where the tissue and debris that differ
between tiles end up. It improves image quality from as few as five tiles
[@doi:10.1038/ncomms14836].

% source: doi:10.1038/ncomms14836

:::{figure} ../images/modules/basic-fig1.jpg
:alt: A mouse brain mosaic with a grid of seams, the BaSiC decomposition into low-rank and residual matrices, and the corrected mosaic without seams.

(a) A whole-slide mosaic with seams from uneven illumination. (c) The BaSiC workflow: tiles
are decomposed into shared shading and a residual. (d) The corrected mosaic. Panels (b) and (e)
show time-lapse correction, which this pipeline does not use. Reproduced from
[@doi:10.1038/ncomms14836], CC BY 4.0.
:::

In this pipeline, BaSiCPy fits only the flat-field; the dark-field file it writes holds no fitted
dark-field.

% source: bin/basicpy_main.py:108-115
% source: bin/basicpy_main.py:211

**Inputs and outputs.** In: the raw tiles of one cycle, as one OME-TIFF (or another
Bio-Formats file such as `.czi`, read tile by tile). Out: two OME-TIFFs per cycle,
`{sample}_cycle{n}-ffp.ome.tif` (flat-field) and `-dfp.ome.tif` (dark-field), one plane per
channel, under `preprocessing/illumination/`. [Ashlar](ashlar.md) reads them while stitching. See
[Preprocessing outputs](../outputs/preprocessing.md).

% source: conf/modules.config:15-24
% source: bin/basicpy_main.py:262-275
% source: docs/output.md#preprocessing

## Similar tools

- **CIDRE** also estimates shading from the images themselves
  ([Smith et al. 2015](https://doi.org/10.1038/nmeth.3323)).
- **Reference images**: a flat-field acquired on a uniform fluorescent slide, or the scanner's
  own shading correction. These need extra acquisitions or vendor software.

BaSiCPy came with the preprocessing half from nf-core/mcmicro. It needs no reference images,
which suits data acquired elsewhere.

% source: doi:10.1038/ncomms14836
% source: docs/decisions.md#architecture

## Read more

- The BaSiC paper: [@doi:10.1038/ncomms14836].
- [BaSiCPy documentation](https://basicpy.readthedocs.io/) and
  [source](https://github.com/peng-lab/BaSiCPy).
- The container, from MCMICRO:
  [labsyspharm/basicpy-docker-mcmicro](https://github.com/labsyspharm/basicpy-docker-mcmicro).

Version used:

```{include} ../_generated/modules/basicpy.md

```
