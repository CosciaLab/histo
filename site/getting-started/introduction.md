# Introduction

## What the pipeline does

You bring the raw images from a multiplex immunofluorescence (mIF) experiment: many small,
overlapping pictures of a tissue section, taken in several rounds of staining. You get back one
table per sample with a row for every cell, its outline, and how bright each marker is inside it,
plus a report that shows whether each step worked.

It does this in two halves:

1. **Preprocessing** turns the raw tiles into one clean image per sample. It evens out the
   uneven lighting of each tile ([BaSiCPy](../modules/basicpy.md)), stitches the tiles into one
   picture and lines up the staining rounds on top of each other ([Ashlar](../modules/ashlar.md)).
   Optionally, it cuts a tissue microarray into its cores ([Coreograph](../modules/coreograph.md))
   and subtracts the tissue's own glow from the markers ([backsub](../modules/backsub.md)).
2. **Analysis** finds the cells in that image and measures them. The image is stored in a format
   built for very large images ([SpatialData](../modules/spatialdata.md)), cut into patches that
   are segmented in parallel ([tiling](../modules/tiling.md)) by
   [Cellpose](../modules/cellpose.md), [InstanSeg](../modules/instanseg.md) or both. Nuclei can be
   linked to their cells ([linking](../modules/linking.md)), every marker is measured per cell
   ([quantification](../modules/quantification.md)), and a [QC report](../modules/qc-report.md)
   checks the result.

The two halves meet at a single stitched OME-TIFF per sample. If your images were already
stitched elsewhere, you can start from the second half.

% source: README.md#what-this-is
% source: README.md#steps
% source: docs/decisions.md#architecture

The preprocessing half comes from [nf-core/mcmicro](https://github.com/nf-core/mcmicro), the
analysis half from [nf-core/sopa](https://github.com/nf-core/sopa). The pipeline follows nf-core
conventions but is not an nf-core pipeline.

% source: README.md#what-this-is

## Who it is for

Bioimage analysts and bench scientists with mIF images of human tissue, including colleagues who do
not program. You describe your experiment in two small tables and a short settings file; the
pipeline does the rest, on a computing cluster, without supervision. Images from 5 GB to
100 GB have run the same way, because segmentation works patch by patch.

% source: README.md#what-this-is
% source: docs/decisions.md#architecture
% source: conf/sizes.config

You do not need to know Nextflow, the workflow system underneath. The
[step-by-step guide](step-by-step.md) covers the few commands you need.

## Scope

What it handles:

- **Cyclic mIF** of tissue sections: several rounds of staining and imaging of the same slide,
  each with a nuclear stain.
- **Whole slides** and **tissue microarrays** (TMAs), where each core is analysed on its own and
  the results are merged per slide.
- **Raw tiles** in any format Ashlar reads (Bio-Formats, for example `.ome.tiff` or `.czi`), or an
  **already stitched** OME-TIFF.

% source: README.md:3-5
% source: docs/output.md#what-runs
% source: docs/decisions.md#the-tma-path

What it does not do: it does not name cell types (phenotyping), cluster cells for biology, or
compute spatial statistics such as neighbourhoods. It stops at a table of measured cells, which is
the starting point for that analysis in tools such as [scanpy](https://scanpy.readthedocs.io) or
[squidpy](https://squidpy.readthedocs.io).

% source: README.md#steps

## mIF today, H&E planned

Today the pipeline reads fluorescence images only. Support for H&E (brightfield) slides is planned
as a separate path through the same pipeline, so that mIF and H&E sections of the same tissue can
be processed side by side. It is not available yet; the
[ROADMAP](https://github.com/CosciaLab/histo/blob/dev/ROADMAP.md) tracks it.

% source: README.md:5
% source: ROADMAP.md:135-136

## Where to go next

- New to imaging? [Experimental background](background.md) explains cycles, channels, tiles and
  what can go wrong with each kind of sample.
- Ready to run? Follow the [step-by-step guide](step-by-step.md), then try
  [tutorial 1](../tutorials/exemplar-001.md) on example data.
- Need every option? The [usage guide](usage-guide.md) and the [inputs](../inputs/inputs.md) pages.
- At the MDC, the [dropbox](../mdc.md) can run the pipeline for you.
