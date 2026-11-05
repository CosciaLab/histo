# Getting started

## Requirements

- Nextflow 25.10.4 or later.
- A container engine: Singularity or Apptainer on the cluster, Docker locally. On Apple Silicon,
  [BaSiCPy](how-it-works/basicpy.md#caveats) and [Coreograph](how-it-works/coreograph.md#caveats)
  do not run.
- The container images, staged before the run. The pipeline pulls nothing at launch; see
  [Fetching images](reference/usage.md#fetching-images).

% source: README.md#usage
% source: nextflow.config:320
% source: docs/usage.md#profiles
% source: docs/CONTRIBUTING.md#on-the-mac

## Nextflow in one paragraph

Nextflow runs each step as a task in its own folder under `work/`, inside a container, locally or
as cluster jobs. `-profile` picks predefined settings (container engine, cluster, resources);
`-params-file` gives the pipeline's parameters; `-resume` reuses finished tasks after a failure or
a change. See the Nextflow docs: [install](https://www.nextflow.io/docs/latest/install.html),
[`-resume` and the work directory](https://www.nextflow.io/docs/latest/cache-and-resume.html),
[profiles](https://www.nextflow.io/docs/latest/config.html#config-profiles).

% source: https://www.nextflow.io/docs/latest/cache-and-resume.html
% source: https://www.nextflow.io/docs/latest/config.html#config-profiles
% source: docs/usage.md#quick-start

## Inputs

Two sheets: a samplesheet (one row per cycle) and a marker sheet (one row per channel). A
pre-stitched image needs only the samplesheet, one row per sample; its channel names come from the
image. Columns are in [Samplesheets](reference/samplesheet.md); how to write and check them is in
[Write and check the input sheets](how-to/input-sheets.md).

% source: docs/usage.md#inputs
% source: docs/usage.md#parameters
% source: site/vignettes/prestitched.md

## Profiles

Give a container engine, a size and, on the cluster, `slurm`, for example
`-profile singularity,size_small,slurm`. All profiles are in
[Profiles](reference/usage.md#profiles).

% source: docs/usage.md#quick-start
% source: docs/usage.md#profiles

## First run

```bash
nextflow run CosciaLab/histo -r v2.0.0 -profile test,laptop -stub --outdir results
```

`test` is a placeholder pre-stitched sample with Cellpose; `-stub` runs every task as a stub, so
it needs no image and no container. It checks that Nextflow and the pipeline start and wire up,
not the tools themselves. `laptop` caps resources to fit a laptop.

% source: conf/test.config
% source: nextflow.config:131-142
% source: docs/CONTRIBUTING.md:29

## Next

Pick the [vignette](vignettes/vignettes.md) closest to your data.
