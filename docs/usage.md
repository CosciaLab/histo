# CosciaLab/histo: Usage

## Quick start

```bash
nextflow run CosciaLab/histo -r v1.3.0 \
    -profile singularity,size_small,slurm \
    -params-file params.yml
```

Give a container engine, a size and, on the cluster, `slurm` (plus `mdc` at the MDC).

Parameters go in `-params-file`, never in `-c`. Custom config files can set anything **except**
parameters.

## Inputs

Two files: a samplesheet and a marker sheet.

**Samplesheet**, one row per acquisition cycle:

```csv
sample,cycle_number,image_tiles,marker_sheet
mysample,1,/abs/path/cycle01.ome.tiff,/abs/path/markers_mysample.csv
mysample,2,/abs/path/cycle02.ome.tiff,/abs/path/markers_mysample.csv
othersample,1,/abs/path/other_cycle01.ome.tiff,/abs/path/markers_other.csv
```

`marker_sheet` is required and names the sheet for that sample. It repeats on every cycle row of a
sample and every copy must be the same file, because the sheet describes the whole stitched image
rather than one cycle of it. Two samples may name different sheets, which is the reason this is a
column rather than a parameter: one run can carry samples with different channel layouts.

Optional `dfp` and `ffp` columns supply pre-computed illumination profiles. If you give them for one
cycle you must give them for all; otherwise BaSiCPy computes them.

**Marker sheet**, one row per channel, `channel_number` running 1..N without gaps:

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,filter
1,1,DNA_1,dna,nuclear,DAPI
2,1,CD45,marker,membrane,FITC
```

`channel_role` is required and states what the pipeline should do with the channel:

| Role               | Meaning                                                                                                                           |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `dna`              | A nuclear stain. Every cycle needs at least one: registration, segmentation and the cross-cycle photobleaching check all read it. |
| `marker`           | A biological readout.                                                                                                             |
| `autofluorescence` | Acquired in order to be subtracted rather than interpreted. This is what `background` must point at.                              |
| `blank`            | Expected to be dark. QC checks that it is, rather than reporting it as a result.                                                  |

Giving the role explicitly is what stops the pipeline guessing which channel is a nuclear stain by
matching its name, which works until someone stains with Hoechst.

`channel_compartment` is optional and states where the signal belongs: `nuclear`, `cytoplasm`,
`membrane`, or a `+`-joined combination such as `nuclear+cytoplasm`. Order is not significant. QC
can only judge whether a marker landed where it should if the sheet says where that is, so leaving
it blank costs a check rather than breaking a run.

`segmentation` is optional and only read with `--use_projection`. It sets which projected
channel a marker feeds: `nuclear`, `cell` or `none`. Without the column, the first `dna` channel is
`nuclear`, and every `marker` whose `channel_compartment` includes `membrane` or `cytoplasm` is
`cell`. Setting it on any row makes the column the whole selection, and blank rows are left out.

`--use_backsub` additionally needs `exposure` and `background` columns. `background` names the
`marker_name` of the channel to subtract, and that channel must itself have `channel_role` set to
`autofluorescence`. The two columns describe one fact, so they are checked against each other.

`remove` set to `true` drops a channel after backsub; without `--use_backsub` it is ignored with a
warning. Keep at least one `dna` channel, and do not name a removed channel in `cellpose_channels`,
`stardist_channels` or `instanseg_channels`; both are rejected at startup.

Ashlar registers every cycle on the same within-cycle channel (`-c` in `ashlar_args`, default
0), and Coreograph dearrays on one channel of the stitched image (`--channel` in
`coreograph_args`). Both may be `-1` for the last channel. The run stops at startup when either
index lands on a channel that is not `dna`; set `skip_reference_dna_check: true` to run anyway.

### When stitching or registration looks wrong

Open the "Stitching and registration" section of the QC report (the slide report on a TMA),
then `preprocessing/registration/{sample}_ashlar_qc/` for detail. What the section shows, and
what to try in `ashlar_args`:

| Symptom in the report                                | Likely cause                                                           | Try                                                           |
| ---------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------- |
| Rejected pairs or several components inside tissue   | Stage error larger than `--maximum-shift`, or a weak alignment channel | Raise `--maximum-shift`; check `-c` is a bright nuclear stain |
| Pair errors overlap the random-strip errors          | Alignment channel has little structure                                 | A different `-c`; `--filter-sigma 1` for noisy images         |
| One cycle with many tiles too far from the model     | Tissue moved or deformed in that cycle                                 | Raise `--maximum-shift`; inspect that cycle's overlay         |
| Kept tiles no better than chance                     | Registration locked onto noise in background tiles                     | Usually harmless at the tissue edge; check the overlay        |
| Overlay shows doubled nuclei everywhere in one cycle | Coarse cycle offset or rotation failed                                 | Check that cycle's dashed outline in the Ashlar PDF           |

Paths must be absolute.

## Parameters

Required: `input`, `outdir` and, unless `preprocessing_only`, one segmentation backend. Cellpose
also needs `cellpose_channels` or `use_projection`. InstanSeg reads every channel unless you name
some. StarDist defaults to sopa's H&E model: for mIF set `stardist_model_type: 2D_versatile_fluo`
and one nuclear `stardist_channels` (untested on real data). Everything else has a default.

**Booleans on the command line follow Nextflow's rule: a bare flag means true, and anything else
means use the default.** `--use_backsub` switches it on. To switch something off, leave it out, or
use a params file where `use_backsub: false` is a real boolean. Writing a value after the flag does
not work and never did: Nextflow reads the flag on its own, sets it true, and throws the value away
before the pipeline sees it, so `--use_backsub false` would perform background subtraction. The
pipeline stops at startup rather than letting that happen, for every boolean it declares.

| Parameter                  | Default              | Change it when                                                                                          |
| -------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------- |
| `use_preprocessing`        | `true`               | Your image is already stitched. Then the samplesheet is one row per sample with a `data_path` column.   |
| `preprocessing_only`       | `false`              | You only want stitched images. No segmentation, quantification or sample QC; Ashlar's QC stays.         |
| `ashlar_args`              | `--maximum-shift 30` | Stitching misaligns.                                                                                    |
| `use_backsub`              | `false`              | You have background channels to subtract.                                                               |
| `skip_reference_dna_check` | `false`              | Ashlar or Coreograph should deliberately use a channel that is not `dna`.                               |
| `use_tma_dearray`          | `false`              | Your slide is a tissue microarray. Each core is then processed alone and the results merged per slide.  |
| `use_cellpose`             | `false`              | Exactly one of `use_cellpose`, `use_stardist` or `use_instanseg` must be true.                          |
| `cellpose_channels`        | none                 | Always, unless `use_projection`. Use a marker name, e.g. `"DNA_1"`.                                     |
| `use_projection`           | `false`              | You want whole cells, not nuclei. See below.                                                            |
| `use_stardist`             | `false`              | You want StarDist nuclei instead of Cellpose. See the note above on its model and channel.              |
| `use_instanseg`            | `false`              | You want InstanSeg instead of Cellpose. Needs `instanseg_pixel_size` (µm per pixel); channels optional. |
| `use_gpu`                  | `false`              | On the cluster: one GPU per Cellpose or InstanSeg patch. See [GPU segmentation](#gpu-segmentation).     |
| `patch_width_pixel`        | none                 | Always. See below.                                                                                      |
| `patch_overlap_pixel`      | none                 | Set to roughly twice a cell diameter.                                                                   |
| `use_tissue_segmentation`  | `false`              | Large empty areas you want skipped.                                                                     |

Every parameter and its default is in two generated files.
[assets/params_template_compact.yml](../assets/params_template_compact.yml) has one line each:
copy it to `params.yml` and uncomment what you change.
[assets/params_template.yml](../assets/params_template.yml) has the full descriptions. `null` in
either means off or unset. `--help` prints the same list.

### Choosing `patch_width_pixel`

This decides whether segmentation parallelises, and it is not automatic. Aim for **16 to 200
patches**: `patch_width_pixel = sqrt(width * height / target_patches)`.

| Stitched image | 2000 | 5000 | 8000 | 10000 |
| -------------- | ---- | ---- | ---- | ----- |
| 3k × 3k        | 4    | 1    | 1    | 1     |
| 25k × 25k      | 169  | 25   | 16   | 9     |
| 50k × 50k      | 625  | 100  | 49   | 25    |
| 115k × 115k    | 3364 | 529  | 225  | 144   |

One patch means no parallelism at all. Thousands means the scheduler costs more than the work.
Memory is not the constraint — a 5000 px patch is about 50 MB.

Get the dimensions with
`python -c "import tifffile; print(tifffile.TiffFile('stitched.ome.tif').series[0].shape)"`.

### Two-channel segmentation (`use_projection`)

Cellpose takes a nuclear and a cell channel, but an mIF panel spreads cell boundaries over many
markers, each on some cell types only. `--use_projection` builds the two channels from the marker
sheet (see `segmentation` above) and segments those; quantification still reads every marker.

Each marker is rescaled between its 1st and 99.9th percentile (zero padding ignored), smoothed with
σ = 1 px, then combined per channel by maximum. Maximum keeps a marker found on one cell type at
full brightness; `projection_method: mean` dims it and loses those cells. On hazy raw images,
`projection_low_percentile: 50` removes the haze from the cell channel.

**Set the Cellpose thresholds when projecting.** Unset, sopa's `flow_threshold: 2`,
`cellprob_threshold: -6` and CLAHE (`clip_limit: 0.2`) tile the whole tissue into cells whatever
the image shows. Cellpose's own values follow the membranes:

```yaml
use_cellpose: true
use_projection: true
flow_threshold: 0.4
cellprob_threshold: 0
clip_limit: 0
```

Check `qc/{sample}_projection.png` first when cells look wrong: it is what Cellpose saw, nuclear in
magenta and cell in green. In the JSON, a marker under `dominant` swamps the others: one diffuse,
bright cytoplasm marker can make Cellpose miss whole groups of cells. Leave it out with the
`segmentation` column. `keep_projection: true` also keeps it at full resolution in the store,
as `<image>_projected`, to view with the cell boundaries. How the defaults were chosen is in
[decisions.md](decisions.md).

## Profiles

**Size** — pick by stitched image size. Only `size_tiny` is derived from measurement; the rest are
estimates and will change.

| Profile       | For                    |
| ------------- | ---------------------- |
| `size_tiny`   | under ~1 GB, test data |
| `size_small`  | up to ~50 GB           |
| `size_medium` | ~50–200 GB             |
| `size_huge`   | ~200 GB and up         |

**Executor** — `slurm`, or omit for local execution. Without it every task runs on the machine you
launched from.

**MDC** — add `mdc` after `slurm` to request nodes with Ceph storage (`--constraint=ceph`).

**Containers** — `singularity` on the cluster. Images must be pre-staged; see
[Fetching images](#fetching-images).

## Example

```yaml
input: /abs/path/samplesheet.csv
outdir: /abs/path/results

use_preprocessing: true

use_cellpose: true
cellpose_channels: "DNA_1"
patch_width_pixel: 1500
patch_overlap_pixel: 50
```

## Running on the cluster

Stage the images first, once per release: see [Fetching images](#fetching-images) below.

Launch from a directory that is **not** the pipeline clone, so run artifacts do not land in the
source tree. Nextflow submits the SLURM jobs itself; you never write an sbatch script. Run it inside
`tmux` so it outlives your session.

```bash
mkdir -p ~/runs/myrun && cd ~/runs/myrun

# Keep temporary files off the shared /tmp, which is small and communal. Without
# this a run dies with "No space left on device" on a path under /tmp, which looks
# like a disk-quota problem and is not one.
export TMPDIR=/fast/AG_Coscia/$USER/tmp
export NXF_TEMP="$TMPDIR"
export NXF_OPTS="-Djava.io.tmpdir=$TMPDIR"
mkdir -p "$TMPDIR"

# Stops a launch-time fetch of a config this pipeline does not use.
export NXF_OFFLINE=true

nextflow run /path/to/histo -profile singularity,size_small,slurm -params-file params.yml -resume
```

All three temp variables are needed for different consumers: `TMPDIR` for tools inside
containers, `NXF_TEMP` for Nextflow's own scratch, and `java.io.tmpdir` for the JVM,
which is the one that fails first and least helpfully.

### GPU segmentation

`use_gpu: true` gives each Cellpose or InstanSeg patch task one GPU; StarDist has no GPU image.
With `-profile …,slurm,mdc` that is an A40 (`--gres=gpu:a40:1`): every A40 node has Ceph, and the
sopa image cannot run on the V100s. At most 16 patches run at once, with 1 CPU and 8 GB on
`size_tiny` and `size_small`, else 2 CPUs and 16 GB. A task fails if CUDA is not usable in it,
rather than running on CPU. Not on the Mac: Docker there has no GPU.

Validate before submitting — this catches bad paths and parameter types in seconds rather than after
a queue wait:

```bash
nextflow run /path/to/histo -profile laptop -stub -params-file params.yml
```

### Fetching images

On a well-connected Linux machine:

```bash
nf-core pipelines download CosciaLab/histo \
    -r <tag> \
    --container-system singularity \
    --outdir ~/histo-download
```

Do this once per release. It resolves every image the pipeline declares and writes the SIFs alongside the pipeline code.

Cross-check what it fetched against the manifest. They should agree, and if they do not, the manifest
generator has a parsing bug rather than the download being wrong:

```bash
nextflow inspect . -profile singularity | grep -o '"container": "[^"]*"' | sort -u
```

### Staging images into the shared cache

Each user sets `NXF_SINGULARITY_CACHEDIR` in their own environment (e.g. `~/.bashrc`); the pipeline
sets no default. At a site it is usually a **shared filesystem path** that colleagues also use.

> [!WARNING]
> Never delete from or overwrite files in the shared cache. Other people's running jobs depend on
> them. Copy in only what is missing.

Check first, copy second:

```bash
# what is already there
ls "$NXF_SINGULARITY_CACHEDIR"

# copy in only new files, never overwriting an existing one
rsync -av --ignore-existing ~/histo-download/singularity-images/ "$NXF_SINGULARITY_CACHEDIR/"
```

`--ignore-existing` rather than plain `rsync` is deliberate: an image already in the cache is one a
colleague may have a job attached to right now, and replacing it mid-run is how you break someone
else's week.
