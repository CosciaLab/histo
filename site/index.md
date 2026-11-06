# CosciaLab/histo

A pipeline that turns raw multiplex immunofluorescence (mIF) images of human tissue into
outlined, measured cells you can analyse: illumination correction, stitching, optional TMA
dearray and background subtraction, then segmentation, quantification and a QC report. It runs
unattended on a cluster, on images of any size. It follows nf-core conventions and is not
affiliated with or endorsed by nf-core.

% source: README.md#what-this-is
% source: README.md#steps

:::{figure} ../docs/images/pipeline_paths.svg
:alt: Metro map of three example paths through the pipeline, from illumination correction to the QC report
Three example paths through the pipeline: a cyclic mIF slide, a whole slide with background
subtraction, and a tissue microarray. [Open the map at full size](../docs/images/pipeline_paths.svg).
:::

% source: docs/pipeline_paths.mmd

::::{grid} 1 2 2 3

:::{card} Getting started
:link: getting-started/introduction.md
What the pipeline does, the imaging background, and a step-by-step first run.
:::

:::{card} Inputs
:link: inputs/inputs.md
The samplesheet, the marker sheet and the parameters.
:::

:::{card} Outputs
:link: outputs/outputs.md
What comes out, and how to read the reports.
:::

:::{card} Tutorials
:link: tutorials/tutorials.md
Complete runs on example data, from a single region to a TMA.
:::

:::{card} Modules
:link: modules/basicpy.md
What each step does, how it works, and why this tool.
:::

:::{card} At the MDC
:link: mdc.md
The dropbox and running on the MDC cluster.
:::

:::{card} Reference
:link: reference/usage.md
The pipeline's usage and output documents, as in the repository.
:::

:::{card} Troubleshooting
[If something fails](getting-started/step-by-step.md#if-something-fails);
[common failures in the results](outputs/reports.md#common-failures).
:::

::::
