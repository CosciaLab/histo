# Usage guide

Everything about launching a run: the command, the profiles, the cluster, resuming and GPUs.
For a first run, read the [step-by-step guide](step-by-step.md) instead. What goes into the
sheets and settings is under [Inputs](../inputs/inputs.md).

## The command

```bash
nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

- `-r` pins the pipeline version. Always give it, so a rerun gives the same result.
- `-profile` picks predefined settings: how software runs, how many resources each step asks for,
  and where the steps run. See [Profiles](#profiles).
- `-params-file` gives your settings. See [Parameters](../inputs/parameters.md).
- `-resume` reuses finished steps of an earlier run. See [Resume a run](#resume-a-run).

% source: docs/usage.md#quick-start
% source: https://www.nextflow.io/docs/latest/cache-and-resume.html

## Settings: file, not command line

Put pipeline settings in the `-params-file`. A setting can also go on the command line as
`--name value`, but two rules make that error-prone:

- **Yes/no settings cannot be switched off on the command line.** Nextflow reads `--use_backsub`
  as "on" and discards whatever follows, so `--use_backsub false` would switch it on. The pipeline
  stops at startup rather than let that happen. In `params.yml`, `use_backsub: false` works.
- **Never put settings in a `-c` config file.** Config files are for cluster and resource
  settings only.

% source: docs/usage.md#parameters
% source: docs/usage.md#quick-start

To start a settings file with every option listed, copy
[`params_template_compact.yml`](https://github.com/CosciaLab/histo/blob/dev/assets/params_template_compact.yml)
to `params.yml` and remove the `#` in front of what you change. `null` there means off or unset.

% source: docs/usage.md#parameters

## Profiles

Give one profile of each kind, separated by commas: `-profile singularity,size_small,slurm`.

**How the software runs.** `singularity` on the cluster (`apptainer` works too); `docker` on a
laptop. The images must be in place before the run; the pipeline downloads nothing while it runs.
How maintainers stage them: [Fetching images](../reference/usage.md#fetching-images).

**Resources.** Pick by the size of the stitched image. Only `size_tiny` is measured; the others
are estimates and will change.

| Profile       | Stitched image         |
| ------------- | ---------------------- |
| `size_tiny`   | under ~1 GB, test data |
| `size_small`  | up to ~50 GB           |
| `size_medium` | ~50–200 GB             |
| `size_huge`   | ~200 GB and up         |

A 16-bit image takes 2 bytes per pixel per channel: 30 000 × 20 000 px with 8 channels is about
10 GB.

**Where the steps run.** `slurm` sends each step to the cluster's queue as its own job. Without
it, everything runs on the machine you launched from.

**At the MDC.** Add `mdc` after `slurm`. It asks for nodes with the Ceph storage, and GPU nodes
when you use a GPU. See [At the MDC](../mdc.md).

% source: docs/usage.md#profiles
% source: conf/sizes.config
% source: conf/mdc.config
% source: nextflow.config:225-235

## Running on the cluster

Launch from a working folder of your own, not from inside a copy of the pipeline. Nextflow submits
the cluster jobs itself; you never write a job script. Run it inside `tmux`, so it keeps going
when you log out.

```bash
mkdir -p ~/runs/myrun && cd ~/runs/myrun
tmux new -s myrun

# Keep temporary files off the shared /tmp, which is small. Without this a run can die
# with "No space left on device", which looks like a quota problem and is not one.
export TMPDIR=/fast/AG_Coscia/$USER/tmp
export NXF_TEMP="$TMPDIR"
export NXF_OPTS="-Djava.io.tmpdir=$TMPDIR"
mkdir -p "$TMPDIR"

# Stops a download at launch of a config this pipeline does not use.
export NXF_OFFLINE=true

nextflow run CosciaLab/histo -r v2.0.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

Replace the `TMPDIR` path with a folder of yours on a large disk. All three temp settings are
needed: they serve the tools, Nextflow and Java respectively.

% source: docs/usage.md#running-on-the-cluster

## Example

A whole slide, about 30 000 × 20 000 px, segmented with Cellpose on many markers, cells and nuclei:

```yaml
input: /data/myproject/sheets/samplesheet.csv
outdir: /data/myproject/results

use_cellpose: true
use_projection: true
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0

segment_nuclei: true
patch_width_pixel: 3000
```

Why each line: [Parameters](../inputs/parameters.md). More complete runs:
[Tutorials](../tutorials/tutorials.md).

% source: docs/usage.md#two-channel-segmentation-use-projection
% source: docs/usage.md#choosing-patch-width-pixel
% source: site/tutorials/multiple-segmentations.md

## Resume a run

Add `-resume` to the same command, from the same working folder, and Nextflow reuses every step
whose inputs and settings have not changed. Use it after a failure, or after changing a setting
that only affects later steps: changing a segmentation setting does not redo the stitching.

Keep `work/` and the hidden `.nextflow/` folder in the working folder; `-resume` needs both.
Results that are links into `work/` (with `publish_dir_mode: symlink`) break when it is deleted.

% source: https://www.nextflow.io/docs/latest/cache-and-resume.html
% source: docs/output.md#pipeline-information

**One exception: the store.** Several steps change a sample's `.zarr` store in place. If a later
run changed the store, `-resume` back to earlier settings reuses those steps and does not bring the
earlier store back. A Cellpose step may also fail with "projection removed by an earlier run".
Rerun those samples without `-resume`.

% source: docs/usage.md#id-resume-and-the-store

To find which steps failed in a past run:

```bash
nextflow log                                        # list the runs
nextflow log <run_name> -f name,status,exit,workdir -F 'status == "FAILED"'
```

% source: https://www.nextflow.io/docs/latest/reference/cli/log

## GPU

`use_gpu: true` gives each Cellpose and InstanSeg patch one GPU. Run it with `slurm`; with `mdc`
too, each patch gets an A40 in the `gpu` partition.

- **At most 16 patches per method run at once.**
- **InstanSeg on GPU takes at most 10 channels**, until its GPU memory is measured. Name 10 or
  fewer in `instanseg_channels`, or the run stops at startup.
- **No silent fallback.** A patch without a usable GPU fails with
  `use_gpu: CUDA is not usable in this task`, rather than running slowly on CPU.
- **Not on a Mac**: Docker there has no GPU.

% source: docs/usage.md#gpu-segmentation
% source: conf/gpu.config
% source: conf/mdc.config
% source: modules/local/segment_patch/main.nf:19

On another cluster whose GPUs sit in their own partition, name it in a config file given with
`-c`; replace `gpu` with your partition. Not needed with `mdc`:

```groovy
process {
    withName: 'SEGMENT_PATCH_(CELLPOSE|INSTANSEG)' {
        queue = 'gpu'
    }
}
```

To check a patch used the GPU, open its work folder's `.command.out`: the `[segment_patch]` line
ends with `device cuda`.

% source: conf/slurm.config:16-17
% source: bin/segment_patch.py:145
