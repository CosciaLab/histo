# Parameters

Every pipeline parameter, grouped as in `nextflow_schema.json`, with its type, default and allowed values.

## Common combinations and conflicts

The run stops at startup when these do not hold:

- **Route.** Raw cycles by default. [`use_preprocessing`](#use_preprocessing)`: false` starts from
  a stitched image ([vignette](../vignettes/prestitched.md)).
  [`preprocessing_only`](#preprocessing_only) ([vignette](../vignettes/stitching-only.md)) and
  [`use_tma_dearray`](#use_tma_dearray) ([vignette](../vignettes/tma.md)) need
  `use_preprocessing`.
- **Method × target.** Unless `preprocessing_only`, at least one of `use_cellpose` and
  `use_instanseg`, and one of `segment_cells` and `segment_nuclei`. See
  [Choose methods and targets](../how-to/segmentation-choices.md).
- **Cellpose channels.** `use_cellpose` needs [`cellpose_channels`](#cellpose_channels) or
  [`use_projection`](#use_projection), not both. `use_projection` needs `use_cellpose` and
  `use_preprocessing`; `keep_projection` needs `use_projection`.
- **InstanSeg.** Needs [`instanseg_pixel_size`](#instanseg_pixel_size); without
  `use_preprocessing` also `instanseg_channels`. With `use_gpu`, at most 10 channels.
- **TMA.** `use_tma_dearray` needs [`tma_expected_cores`](#tma_expected_cores) and
  [`tma_core_diameter_mm`](#tma_core_diameter_mm), both above 0, unless `coreograph_args` is set.
- **Booleans on the command line:** see [Parameters](usage.md#parameters).

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:648-704
% source: modules/local/utils.nf:89
% source: modules/local/utils.nf:142

Each parameter below carries these as a **Requires**, **Conflicts** or **Ignored unless** line.

% source: nextflow_schema.json

```{include} ../_generated/parameters.md

```
