# Segmentation benchmark

Scores Cellpose-SAM (`cpsam_v2`, diameter 30) against ground-truth masks on three public
datasets (Cross-platform, Tonsil, TissueNet). One SLURM array task runs one setting of the
preprocessing/threshold grid (`settings.csv`, 168 rows) over its crops and writes
`results/<N>.csv` (F1 and AP at IoU 0.5-0.9 per crop). Montage crops also write their labels.
Data never enters the repo.

## Steps

1. Prepare on the Mac (raw downloads to one crop layout):
   `python tools/segmentation_benchmark/prepare.py --raw $RAW --out $BENCH/data`
2. Copy data and repo to cluster scratch:
   `rsync -a $BENCH/data/ cluster:$SCRATCH/bench/data/` and
   `rsync -a --exclude .git ./ cluster:$SCRATCH/bench/repo/`
3. Timing job first (today's cells/raw setting, 20 crops); `--time` on the command line
   overrides the placeholder, extra arguments go to `run.py`. It writes `results/18.partial.csv`,
   which the full array ignores:
   `sbatch --array=18 --time=01:00:00 tools/segmentation_benchmark/run_array.sbatch --limit-crops 20`
   Use its seconds to set `--time` in the sbatch.
4. Full array:
   `export SIF=... DATA=$SCRATCH/bench/data OUT=$SCRATCH/bench/out REPO=$SCRATCH/bench/repo`
   `sbatch --array=0-167%8 tools/segmentation_benchmark/run_array.sbatch`
   Set the partition line in the script first. Finished settings are skipped on resubmit.
5. Copy back and report: `rsync -a cluster:$SCRATCH/bench/out/{results,labels} $BENCH/out/`, then
   `python tools/segmentation_benchmark/report.py --results $BENCH/out/results --data $BENCH/data --out $BENCH/out/report`

## Data layout

`data/crops.csv` lists every crop; each has `data/crops/<dataset>/<crop>/image.tif` (C,Y,X) and
`cells.tif` and/or `nuclei.tif`. A target is scored only where its mask file exists.
Settings 0-143 are cells on Cross-platform and Tonsil, 144-155 cells on TissueNet, 156-167
nuclei on all three.

## Licences and tokens

TissueNet: non-commercial use. Cross-platform: CC BY 4.0 (per its paper). Tonsil: CC BY 4.0.
Download tokens (Synapse) live in `~/.synapseConfig`, never in the repo.
