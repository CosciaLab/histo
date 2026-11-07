#!/bin/bash
#SBATCH --job-name=seg-bench
#SBATCH --array=0-167%8
# Set the partition for your cluster, then uncomment: --partition=<name>
##SBATCH --partition=
#SBATCH --gres=gpu:a40:1
#SBATCH --constraint=ceph
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00  # generous; tighten after the timing job
#SBATCH --output=logs/%A_%a.out
# Submit from a directory where logs/ exists. Needs SIF, DATA, OUT and REPO in the environment.
set -euo pipefail

: "${SIF:?set SIF to the sopa 2.3.0 .sif image}"
: "${DATA:?set DATA to the prepared data directory}"
: "${OUT:?set OUT to the results directory}"
: "${REPO:?set REPO to the repository root (sbatch copies this script)}"

apptainer exec --nv --bind "$DATA" --bind "$OUT" --bind "$REPO" "$SIF" \
    python "$REPO/tools/segmentation_benchmark/run.py" \
    --data "$DATA" --setting-index "$SLURM_ARRAY_TASK_ID" --out "$OUT" --gpu "$@"
