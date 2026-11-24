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
   overrides the 4 h default, extra arguments go to `run.py`. It writes `results/18.partial.csv`,
   which the full array ignores:
   `sbatch --array=18 --time=01:00:00 tools/segmentation_benchmark/run_array.sbatch --limit-crops 20`
   Use its seconds to set `--time` in the sbatch.
4. Full array:
   `export SIF=... DATA=$SCRATCH/bench/data OUT=$SCRATCH/bench/out REPO=$SCRATCH/bench/repo`
   `sbatch --array=0-167%8 tools/segmentation_benchmark/run_array.sbatch`
   Set the partition line in the script first. Finished settings are skipped on resubmit.
5. Copy back and report: `rsync -a cluster:$SCRATCH/bench/out/{results,labels} $BENCH/out/`, then
   `python tools/segmentation_benchmark/report.py --results $BENCH/out/results --data $BENCH/data --out $BENCH/out/report`

## Round 2

`settings_round2.csv`, 307 rows, on round 1's best preprocessing (max, percentile 1, no
smoothing, no CLAHE):

- 0-167: cells on Cross-platform and Tonsil, 7 `flow_threshold` x 8 `cellprob_threshold`, for
  each cell channel selection: `markers` (no autofluorescence; the baseline), `all` (round 1),
  `membrane` (also no nuclear-localised markers).
- 168-223: cells on TissueNet; 224-279: nuclei on all three (no projection smoothing).
- 280-306: CLAHE 0.01 at 9 threshold pairs, one block per target.

The pick is one threshold pair for nuclei and cells: the smallest worst shortfall from the best
on cells and nuclei, Cross-platform and TissueNet. Tonsil is reported, not used.

1. Prepare as above into a new folder (Vectra channel names come from the TIFF metadata):
   `--out $BENCH/data_round2`, then rsync it to the cluster.
2. `sbatch --array=0-306%8 --time=00:30:00 tools/segmentation_benchmark/run_array.sbatch --grid round2`
   with `DATA` and `OUT` pointing at the round-2 folders.
3. `python tools/segmentation_benchmark/report_round2.py --results $BENCH/out_round2/results --out $BENCH/out_round2/report --round1 $BENCH/out/results`
   (`--round1` checks that the six settings both rounds share give the same F1).

## Data layout

`data/crops.csv` lists every crop; each has `data/crops/<dataset>/<crop>/image.tif` (C,Y,X) and
`cells.tif` and/or `nuclei.tif`. A target is scored only where its mask file exists.
Settings 0-143 are cells on Cross-platform and Tonsil, 144-155 cells on TissueNet, 156-167
nuclei on all three.

## Licences and tokens

TissueNet: non-commercial use. Cross-platform: CC BY 4.0 (per its paper). Tonsil: CC BY 4.0.
Download tokens (Synapse) live in `~/.synapseConfig`, never in the repo.
