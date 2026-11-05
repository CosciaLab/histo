# CosciaLab/histo

A Nextflow pipeline for multiplex immunofluorescence (mIF) images of human tissue: illumination
correction, stitching and registration, optional TMA dearray and background subtraction, then
tiled segmentation, quantification and QC. Preprocessing comes from nf-core/mcmicro, everything
from segmentation onward from nf-core/sopa; the handoff is one stitched OME-TIFF. It follows
nf-core conventions and is not affiliated with or endorsed by nf-core.

% source: README.md#what-this-is
% source: README.md#steps

:::{figure} ../docs/images/pipeline_paths.svg
:alt: Metro map of the three paths through the pipeline
[Open the map at full size](../docs/images/pipeline_paths.svg).
:::

% source: README.md#steps

::::{grid} 1 2 2 3

:::{card} Getting started
:link: getting-started.md
Install, inputs, profiles and a first test run.
:::

:::{card} Vignettes
:link: vignettes/vignettes.md
Complete runs for common cases.
:::

:::{card} How-to guides
:link: how-to/how-to.md
Short recipes, one task each.
:::

:::{card} How it works
:link: how-it-works/how-it-works.md
What each step does and why.
:::

:::{card} Outputs
:link: outputs/outputs.md
What comes out and how to read the QC.
:::

:::{card} Reference
:link: reference/usage.md
Usage, parameters, sheets and outputs.
:::

:::{card} At the MDC
:link: mdc.md
The dropbox and running on the MDC cluster.
:::

:::{card} Troubleshooting
[Resume and debug a run](how-to/resume-debug.md); [common failures](outputs/visual-qc.md#common-failures).
:::

::::
