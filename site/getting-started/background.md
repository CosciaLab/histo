# Experimental background

What happens at the microscope, and why each step of the pipeline exists. Skip this if you
acquire mIF images yourself.

## Staining and imaging

A thin section of tissue on a glass slide is stained with antibodies, each carrying a fluorescent
dye. A fluorescence microscope shines light of one colour on it and records the light the dye
gives back, through a filter for that dye. Each filter gives one greyscale picture, a
**channel**, showing where one marker sits. A nuclear stain such as DAPI or Hoechst marks every
nucleus.

A microscope sees only a small field at a time, so a slide is imaged as a grid of overlapping
**tiles**. Tiles overlap by a margin so they can be matched to each other afterwards.

% source: docs/usage.md#inputs
% source: doi:10.1093/bioinformatics/btac544

## Cycles

A microscope separates only four or five dyes at once. **Cyclic** mIF gets past that: stain and
image four or five markers, remove or bleach the dyes, stain the next set, image again. Each
round is a **cycle**; ten cycles give dozens of markers on the same cells.

Every cycle images a nuclear stain again. The nuclei are the landmarks that line the cycles up,
because the slide never goes back to exactly the same place on the stage.

% source: docs/usage.md#inputs
% source: docs/decisions.md#channel-projection

In the pipeline's terms: one row of the [samplesheet](../inputs/samplesheet.md) per cycle, and one
row of the [marker sheet](../inputs/markers.md) per channel across all cycles.

## Autofluorescence

Tissue glows a little on its own, especially in green and red: collagen, red blood cells and
fixation all add light that no antibody put there. Some experiments image a cycle with no
antibodies at all, to record this **autofluorescence** and subtract it from the markers later.
That is what [background subtraction](../modules/backsub.md) does.

% source: docs/usage.md#inputs
% source: site/modules/backsub.md

## Whole slides and tissue microarrays

A **whole-slide image** (WSI) covers one large section: tens of thousands of pixels on a side,
often tens to hundreds of GB.

A **tissue microarray** (TMA) holds many small, round cores of tissue, often from different
patients, on one slide. Each core is about 0.6 to 2 mm across. The pipeline finds the cores
([Coreograph](../modules/coreograph.md)), analyses each on its own, and merges the results per
slide.

% source: docs/decisions.md#the-tma-path
% source: conf/sizes.config

## Pixel size

Each pixel covers a fixed width of tissue, for example 0.65 µm in the tutorials' example data.
The stitched image records it in its metadata. Cell areas in the results are in pixels²; multiply by the pixel
size squared for µm².

% source: docs/decisions.md#pixel-size
% source: conf/test_exemplar001.config

## Why the image needs preprocessing

- **Uneven lighting.** A tile is brighter in the middle than at the edges. Without correction, a
  stitched image shows a grid of seams, and a cell's brightness depends on where in its tile it
  sat. [BaSiCPy](../modules/basicpy.md) corrects this.
- **Stitching.** The stage does not move exactly as asked, so tiles must be matched by their
  overlaps, not placed by their nominal positions.
- **Registration.** Each cycle must land exactly on the first, or a cell's markers from different
  cycles would come from different places. [Ashlar](../modules/ashlar.md) does both.

% source: doi:10.1038/ncomms14836
% source: doi:10.1093/bioinformatics/btac544

## What comes out

**Segmentation** draws an outline around every cell, and optionally around every nucleus.
**Quantification** then measures each marker inside each outline: one row per cell, one column per
marker and statistic (mean, median, standard deviation), plus the cell's area and position. That
table is what you analyse. See [Outputs](../outputs/outputs.md).

% source: docs/output.md#spatialdata-directory
% source: nextflow_schema.json (quantification_statistics)

## What to watch for by type of data

### Cyclic mIF

- **Cells are lost between cycles.** Repeated staining washes some tissue off, so later cycles
  show fewer cells. By default the pipeline finds nuclei on the first cycle's nuclear stain,
  and the QC report compares the nuclear stain of the first and last cycle per cell to show the
  loss. See [projection](../modules/projection.md) and the [QC report](../modules/qc-report.md).
- **Every cycle needs a nuclear stain**, marked `dna` in the marker sheet. Registration and the
  cross-cycle check read it.
- **A poor registration does not stop the run.** Always look at the report's "Stitching and
  registration" section. See [Ashlar](../modules/ashlar.md#when-stitching-looks-wrong).

% source: docs/decisions.md#channel-projection
% source: docs/output.md#qc-report
% source: docs/usage.md#inputs
% source: docs/usage.md#when-stitching-or-registration-looks-wrong

### Tissue microarrays

- **Each core is analysed alone**, then the cores are merged per slide.
- **Finding the cores needs two numbers from you**: how many cores and how wide. A wrong guess
  can split or merge cores without an error, so look at the core map. See
  [Coreograph](../modules/coreograph.md).
- **One unreadable or empty core stops the whole slide.** It is not skipped.
- **Stitching is per slide.** If it fails, every core on that slide fails with it.

% source: docs/decisions.md#the-tma-path
% source: docs/usage.md#tma-dearray
% source: docs/decisions.md#segmentation

### Whole slides

- **Size is not the limit**, but the patch size must be set for large images: aim for 16 to 200
  patches. See [patch size](../inputs/parameters.md#patch-size).
- **Empty glass can be skipped** with tissue detection, which is off by default. See
  [skip empty glass](../inputs/parameters.md#skip-empty-glass).
- **Background subtraction is optional**, and can also be done later on the measured table.

% source: docs/usage.md#choosing-patch-width-pixel
% source: site/modules/tiling.md
% source: site/modules/backsub.md

### Pixel size

- **InstanSeg needs the pixel size from you** (`instanseg_pixel_size`); it does not read it from
  the image.
- **Finding TMA cores reads it from the image.** Without it, core detection stops and asks for
  manual settings.

% source: docs/decisions.md#pixel-size
% source: site/modules/coreograph.md
% source: site/modules/instanseg.md

### H&E

- **Not supported yet.** Only fluorescence images work today; see the
  [introduction](introduction.md).

% source: README.md:5
% source: ROADMAP.md:135
