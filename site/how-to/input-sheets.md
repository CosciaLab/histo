# Write and check the input sheets

Goal: a samplesheet and marker sheets that pass validation, checked before a long run.

## Steps

1. Write the samplesheet, one row per cycle. Every column is on
   [Samplesheets](../reference/samplesheet.md#cycle-sheet); an example is in
   [Inputs](../reference/usage.md#inputs). Use absolute paths without spaces.
2. Number each sample's cycles 1..N, without gaps or repeats, and give every row of a sample the
   same `marker_sheet`.
3. Write one marker sheet per channel layout, one row per channel across all cycles
   ([columns](../reference/samplesheet.md#marker-sheet)). `channel_number` runs 1..N without
   restarting per cycle, `marker_name` is unique, and every cycle has a `dna` channel.
4. Put the nuclear stain at the same position in every cycle. Ashlar aligns every cycle on one
   within-cycle channel (`-c` in `ashlar_args`, default the first), and the run stops if that is
   not `dna`.
5. Add the columns your options read: `exposure` and `background` for
   [`use_backsub`](../reference/parameters.md#use_backsub); `channel_compartment` or
   `segmentation` for [`use_projection`](../reference/parameters.md#use_projection).

% source: assets/schema_input_cycle.json
% source: assets/schema_marker.json
% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:241-316
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-500

## Check before a long run

A `-stub` run validates both sheets and the parameters in seconds, without containers. It writes
placeholder outputs, so point `--outdir` at a scratch directory and launch from there:

```bash
mkdir -p ~/scratch/histo-check && cd ~/scratch/histo-check
nextflow run CosciaLab/histo -r v2.0.0 -profile laptop -stub \
    -params-file /path/to/params.yml --outdir ~/scratch/histo-check/results
```

`--outdir` on the command line overrides the one in `params.yml`. A failing check stops the run
and names the sample, the sheet and the column. Delete `~/scratch/histo-check` afterwards.

% source: docs/usage.md:301-306
% source: nextflow.config:130-141
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:143-162
% source: https://www.nextflow.io/docs/latest/cli.html (parameter precedence)
% source: https://www.nextflow.io/docs/latest/reference/cli/run (-stub)

## Pitfalls

- **A stub does not open the images.** That the marker sheet lists as many channels as the
  stitched image has is checked only after stitching, in `SET_CHANNEL_NAMES`.
- **`remove` without `use_backsub`** is ignored, with a warning.

% source: bin/set_channel_names.py:94-102
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:364-371
