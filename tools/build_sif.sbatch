#!/usr/bin/env bash
#
# Build an Apptainer SIF from a Docker image, straight into Nextflow's singularity cache.
#
# Usage (from the repo root, on the cluster, after sourcing histo's setup.sh):
#   sbatch tools/build_sif.sbatch [--name FILE] [--force] [--need-gb N] <source> [out_dir]
#   bash tools/build_sif.sbatch --help
#
#   <source>   a registry ref, e.g. docker.io/josenimo/nimbus:0.0.5 (docker:// optional),
#              or a local docker-save tar, OCI archive, or OCI layout directory (no network).
#   out_dir    default $NXF_SINGULARITY_CACHEDIR, else the histo cache:
#              /fast/AG_Coscia/software/pipelines/histo/singularity-images
#   --name     output file name. Default for a ref: Nextflow's cache name, e.g.
#              docker.io-josenimo-nimbus-0.0.5.img. Required for a local source.
#   --force    replace an existing file in out_dir. Refused in the shared cache: use a new tag.
#   --need-gb  free space to require (default 60 for a ref, 4x the source size for a file).
#
# The output is a SIF either way; `.img` is only the name Nextflow looks for. It is built as
# <name>.partial.<jobid> and renamed once verified, so Nextflow never sees half an image.
# Log:   <histo cache>/logs/build_sif.<jobid>.log (sbatch -o elsewhere.log to change).
# Temp:  $APPTAINER_TMPDIR and $APPTAINER_CACHEDIR (setup.sh sets both), else
#        /fast/AG_Coscia/software/nextflow/$USER/apptainer_{tmp,cache}.
# Tests set BUILD_SIF_ATTEMPTS and BUILD_SIF_RETRY_SLEEP (default 4 attempts, 60 s doubling).

# mksquashfs scales to ~16 threads; past that the /fast write is the limit.
#SBATCH --cpus-per-task=16
# Twice the mksquashfs cache, plus room for extraction; covers 25% of a 176 GB node on Apptainer < 1.4.
#SBATCH --mem=48G
# A ~14 GB image pulls and squashes in under an hour; the rest is slack for retries.
#SBATCH --time=04:00:00
# MDC default partition (7 d); no GPU needed.
#SBATCH --partition=normal
# /fast is only mounted on Ceph nodes.
#SBATCH --constraint=ceph
#SBATCH --job-name=build_sif
# SLURM expands no variables here and creates no directories: keep in step with default_cache.
#SBATCH --output=/fast/AG_Coscia/software/pipelines/histo/singularity-images/logs/%x.%j.log
#SBATCH --error=/fast/AG_Coscia/software/pipelines/histo/singularity-images/logs/%x.%j.log

set -euo pipefail
# Colleagues read the copy in the shared cache; rsync -a keeps these permissions.
umask 022

# The header comment, up to the first blank line.
usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "${BASH_SOURCE[0]}"; }
stage() { printf '\n==== [%s] %s\n' "$(date '+%F %T')" "$*"; }
info() { printf '  %s\n' "$*"; }
die() {
    printf '\nERROR: %s\n' "$1" >&2
    shift
    for hint in "$@"; do printf '  -> %s\n' "$hint" >&2; done
    exit 1
}

# Physical path of $1, even if it does not exist yet.
resolve() {
    local p="$1" rest=""
    while [[ ! -d "$p" ]]; do
        rest="/$(basename "$p")$rest"
        p="$(dirname "$p")"
    done
    p="$(cd "$p" && pwd -P)"
    printf '%s%s' "${p%/}" "$rest"
}

# Nextflow SingularityCache.simpleName: '.img' unless the name carries '.sif'.
nxf_cache_name() {
    local n="$1" ext=".img"
    if [[ "$n" == *.sif:* ]]; then
        ext=".sif"
        n="${n//.sif:/-}"
    elif [[ "$n" == *.sif ]]; then
        ext=".sif"
        n="${n%.sif}"
    fi
    n="${n//:/-}"
    n="${n//\//-}"
    printf '%s%s' "$n" "$ext"
}

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }

# ---------------------------------------------------------------------------- arguments

name="" force=0 need_gb=""
positional=()
while (($#)); do
    case "$1" in
        -h | --help) usage; exit 0 ;;
        --force) force=1 ;;
        --name)
            [[ $# -ge 2 ]] || die "--name needs a value" "see --help"
            name="$2"
            shift
            ;;
        --need-gb)
            [[ $# -ge 2 ]] || die "--need-gb needs a value" "see --help"
            need_gb="$2"
            shift
            ;;
        -*) die "unknown option: $1" "see: bash tools/build_sif.sbatch --help" ;;
        *) positional+=("$1") ;;
    esac
    shift
done
((${#positional[@]} >= 1 && ${#positional[@]} <= 2)) ||
    die "expected <source> [out_dir], got ${#positional[@]} arguments" "see: bash tools/build_sif.sbatch --help"
[[ -z "$need_gb" || "$need_gb" =~ ^[0-9]+$ ]] || die "--need-gb must be a whole number of GB, got '$need_gb'"

source_arg="${positional[0]}"
default_cache=/fast/AG_Coscia/software/pipelines/histo/singularity-images
# Where generic_setup.sh puts each user's apptainer dirs.
user_base="/fast/AG_Coscia/software/nextflow/${USER:?USER is not set}"
out_dir="${positional[1]:-${NXF_SINGULARITY_CACHEDIR:-${NXF_APPTAINER_CACHEDIR:-$default_cache}}}"
job_id="${SLURM_JOB_ID:-local.$$}"
cpus="${SLURM_CPUS_PER_TASK:-4}"
mem_mb="${SLURM_MEM_PER_NODE:-8192}"
attempts="${BUILD_SIF_ATTEMPTS:-4}"
retry_sleep="${BUILD_SIF_RETRY_SLEEP:-60}"

# ---------------------------------------------------------------------------- source

if [[ -e "$source_arg" ]]; then
    mode=local
    src_abs="$(resolve "$source_arg")"
    if [[ -d "$src_abs" ]]; then
        if [[ -f "$src_abs/oci-layout" && -f "$src_abs/index.json" ]]; then
            bootstrap="oci://$src_abs"
        elif [[ -f "$src_abs/manifest.json" ]]; then
            die "$src_abs looks like an unpacked docker save" "pass the .tar from docker save instead"
        else
            die "$src_abs is not an OCI layout directory (needs oci-layout and index.json)"
        fi
    else
        header="$(head -c 64 "$src_abs" | LC_ALL=C tr -d '\0')"
        if [[ "$header" == *SIF_MAGIC* || "${header:0:4}" == hsqs || "$src_abs" == *.sif || "$src_abs" == *.img ]]; then
            echo "$src_abs is already an Apptainer image; nothing to build."
            echo "To stage it, rename it to the Nextflow cache name and copy it without overwriting:"
            echo "  rsync -av --ignore-existing <renamed file> \"\$NXF_SINGULARITY_CACHEDIR/\""
            exit 0
        fi
        # Contents, not the extension, decide the bootstrap. A few dozen members, so a variable is fine.
        members="$(tar -tf "$src_abs" 2>/dev/null | sed -e 's|^\./||' -e 's|/$||')" ||
            die "$src_abs is not a readable tar archive" "expected the output of 'docker save' or an OCI archive"
        # docker save from Docker 25+ also writes index.json, so manifest.json decides first.
        if grep -qx 'manifest.json' <<<"$members"; then
            bootstrap="docker-archive://$src_abs"
        elif grep -qx 'oci-layout' <<<"$members" && grep -qx 'index.json' <<<"$members"; then
            bootstrap="oci-archive://$src_abs"
        else
            die "$src_abs has neither manifest.json (docker save) nor oci-layout and index.json (OCI)" \
                "list it with: tar -tf $src_abs | head"
        fi
    fi
    if [[ -z "$need_gb" ]]; then
        # Unpacking needs 3-4x the compressed size; 20 GB floor for small images.
        src_kb="$(du -sk "$src_abs" | awk '{print $1}')"
        need_gb=$(((src_kb * 4 + 1048575) / 1048576))
        ((need_gb >= 20)) || need_gb=20
    fi
    [[ -n "$name" ]] || die "--name is required for a local source" \
        "use the name Nextflow looks for: the container string with ':' and '/' as '-', plus .img" \
        "e.g. container docker.io/josenimo/nimbus:0.0.5 -> --name docker.io-josenimo-nimbus-0.0.5.img"
elif [[ "$source_arg" == /* || "$source_arg" == .* || "$source_arg" =~ \.(tar|tar\.gz|tgz|sif|img)$ ]]; then
    die "no such file or directory: $source_arg" "check the path; a registry ref looks like docker.io/user/image:tag"
else
    mode=registry
    ref="${source_arg#docker://}"
    [[ "$ref" != *://* ]] || die "unsupported scheme in '$source_arg'" "give a docker:// ref or a local path"
    [[ "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/:@-]*$ ]] || die "not a valid image reference: '$ref'"
    last="${ref##*/}"
    [[ "$last" == *:* || "$last" == *@* ]] ||
        die "'$ref' has no tag" "pin one, e.g. $ref:1.0; :latest changes under you and Nextflow names files by tag"
    bootstrap="docker://$ref"
    [[ -n "$need_gb" ]] || need_gb=60
    [[ -n "$name" ]] || name="$(nxf_cache_name "$ref")"
fi

[[ "$name" != */* && "$name" != .* && "$name" =~ \.(img|sif)$ ]] ||
    die "bad --name '$name'" "a plain file name ending in .img or .sif"

# ---------------------------------------------------------------------------- paths

# First candidate that is set and not under /tmp (small, and shared on login and compute nodes).
first_off_tmp() {
    local d
    for d in "$@"; do
        if [[ -n "$d" && "$d" != /tmp && "$d" != /tmp/* ]]; then
            printf '%s' "$d"
            return
        fi
    done
}
tmp_base="$(first_off_tmp "${APPTAINER_TMPDIR:-}" "${TMPDIR:-}" "$user_base/apptainer_tmp")"
APPTAINER_CACHEDIR="$(first_off_tmp "${APPTAINER_CACHEDIR:-}" "$user_base/apptainer_cache")"

out_dir="$(resolve "$out_dir")"
tmp_base="$(resolve "$tmp_base")"
APPTAINER_CACHEDIR="$(resolve "$APPTAINER_CACHEDIR")"
# Same value under both names, or apptainer warns that they differ.
export APPTAINER_CACHEDIR SINGULARITY_CACHEDIR="$APPTAINER_CACHEDIR"

# Shared caches: Nextflow reads them, and colleagues' running jobs may hold their images.
shared_caches=()
for c in "${NXF_SINGULARITY_CACHEDIR:-}" "${NXF_APPTAINER_CACHEDIR:-}" "$default_cache"; do
    if [[ -n "$c" ]]; then shared_caches+=("$(resolve "$c")"); fi
done
in_cache=0
for c in "${shared_caches[@]}"; do
    if [[ "$out_dir" == "$c" ]]; then
        in_cache=1
    elif [[ "$out_dir" == "$c"/* ]]; then
        die "$out_dir is below the cache $c" "Nextflow only looks in $c itself; pass that, or a directory outside it"
    fi
    for d in "$tmp_base" "$APPTAINER_CACHEDIR"; do
        if [[ "$d" == "$c" || "$d" == "$c"/* ]]; then
            die "$d is inside the cache $c" "point APPTAINER_TMPDIR, TMPDIR or APPTAINER_CACHEDIR elsewhere"
        fi
    done
done

final="$out_dir/$name"
partial="$out_dir/$name.partial.$job_id"
job_tmp="$tmp_base/build_sif.$job_id"
export APPTAINER_TMPDIR="$job_tmp" SINGULARITY_TMPDIR="$job_tmp"

if [[ -e "$final" && "$in_cache" -eq 1 ]]; then
    # Each Nextflow task opens the image by name, so a replacement would mix images within a run.
    die "$final is already in the cache" "nothing to build; to change the image, push a new tag" \
        "or build elsewhere (pass an out_dir) and compare sha256 first"
elif [[ -e "$final" && "$force" -eq 0 ]]; then
    die "$final already exists" "pass --force to replace it, or choose another out_dir or --name"
fi

cleanup() {
    if [[ -e "$partial" ]]; then rm -f -- "$partial"; fi
    # Literal job-specific suffix, so this can never match anything but our own directory.
    if [[ "$job_tmp" == */build_sif."$job_id" && -d "$job_tmp" ]]; then
        rm -rf -- "$job_tmp" 2>/dev/null || { chmod -R u+w -- "$job_tmp" && rm -rf -- "$job_tmp"; } ||
            echo "WARNING: could not remove $job_tmp; delete it by hand" >&2
    fi
}
trap cleanup EXIT
# SLURM sends TERM at timeout or scancel; exiting runs the EXIT trap.
trap 'echo "Interrupted; cleaning up" >&2; exit 143' TERM INT

# ---------------------------------------------------------------------------- environment

stage "Environment"
info "host:        $(hostname)"
info "slurm job:   ${SLURM_JOB_ID:-none (not under sbatch)}"
info "cpus / mem:  $cpus / ${mem_mb} MB"
command -v apptainer >/dev/null ||
    die "apptainer is not on PATH" "load it (e.g. module load apptainer) or check the node; see 'which apptainer'"
info "apptainer:   $(apptainer --version)"
info "source:      $bootstrap"
info "output:      $final$( ((in_cache)) && printf ' (shared cache)')"
if [[ -n "${SLURM_JOB_ID:-}" ]] && command -v scontrol >/dev/null; then
    info "log:         $(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | sed -n 's/^ *StdOut=//p')"
fi
info "tmp:         $APPTAINER_TMPDIR"
info "cache:       $APPTAINER_CACHEDIR"
if [[ "$mode" == registry ]]; then
    if [[ -n "${APPTAINER_DOCKER_USERNAME:-}" && -n "${APPTAINER_DOCKER_PASSWORD:-}" ]]; then
        info "registry:    credentials from APPTAINER_DOCKER_USERNAME/PASSWORD"
    else
        info "registry:    anonymous (Docker Hub rate limits apply)"
    fi
fi

for d in "$out_dir" "$job_tmp" "$APPTAINER_CACHEDIR"; do
    mkdir -p -- "$d" || die "cannot create $d" "check the path and that you can write there"
done
# A killed job (OOM, node failure) skips the cleanup trap; a parallel job is building the same name.
for stale in "$final".partial.*; do
    if [[ -e "$stale" ]]; then info "WARNING: found $stale (a running build, or a killed one's leftover)"; fi
done

# ---------------------------------------------------------------------------- disk space

stage "Check free space (need ${need_gb} GB per location)"
for d in "$job_tmp" "$out_dir"; do
    avail_kb="$(df -Pk "$d" | awk 'NR == 2 {print $4}')"
    avail_gb=$((avail_kb / 1048576))
    info "$d: ${avail_gb} GB free"
    ((avail_gb >= need_gb)) ||
        die "not enough space in $d: ${avail_gb} GB free, ${need_gb} GB needed" \
            "free space there, set TMPDIR or out_dir elsewhere, or lower the check with --need-gb"
done

# ---------------------------------------------------------------------------- build

stage "Build $bootstrap"
build_args=(build)
help_text="$(apptainer build --help 2>&1 || true)"
if [[ "$help_text" == *--mksquashfs-args* ]]; then
    # mksquashfs sees the whole node, not the job: cap threads and its cache (default 25% of node RAM).
    build_args+=(--mksquashfs-args "-processors $cpus -mem $((mem_mb / 2))M")
else
    info "WARNING: this apptainer has no --mksquashfs-args (needs >= 1.4); mksquashfs will use every CPU it sees"
fi
build_args+=("$partial" "$bootstrap")
info "command: apptainer $(printf '%q ' "${build_args[@]}")"

if [[ "$mode" == registry ]]; then
    attempt=1
    until apptainer "${build_args[@]}"; do
        rm -f -- "$partial"
        if ((attempt >= attempts)); then
            die "apptainer build failed $attempts times for docker://$ref" \
                "check the ref exists: tag spelling, registry, public or private" \
                "check this node reaches the registry: curl -sI https://registry-1.docker.io/v2/" \
                "rate limited? export APPTAINER_DOCKER_USERNAME and APPTAINER_DOCKER_PASSWORD, then resubmit" \
                "resubmitting reuses layers already in $APPTAINER_CACHEDIR"
        fi
        wait_s=$((retry_sleep * 2 ** (attempt - 1)))
        info "attempt $attempt of $attempts failed; retrying in ${wait_s} s"
        sleep "$wait_s"
        attempt=$((attempt + 1))
    done
else
    apptainer "${build_args[@]}" ||
        die "apptainer build failed for $bootstrap" "see the apptainer output above" \
            "check the archive is complete: compare its size or sha256 with the machine it came from"
fi

# ---------------------------------------------------------------------------- verify

stage "Verify"
apptainer inspect "$partial" || die "apptainer inspect failed on the new image" "see the output above; rebuild"
# Nextflow runs every task with bash inside the image.
apptainer exec "$partial" /bin/bash -c true ||
    die "the image cannot run /bin/bash" "Nextflow needs bash in the image; check the Dockerfile"

if [[ -e "$final" ]] && ((in_cache || !force)); then
    die "$final appeared during the build" "check for a parallel job; the new image is discarded"
fi
mv -f -- "$partial" "$final"

stage "Done"
info "file:     $final"
info "size:     $(du -h -- "$final" | cut -f1) ($(wc -c <"$final" | tr -d ' ') bytes)"
info "sha256:   $(sha256 "$final" | cut -d' ' -f1)"
info "format:   SIF (the .img suffix is only Nextflow's cache naming)"
if ((in_cache)); then
    echo
    echo "Nextflow will use it from $out_dir."
    exit 0
fi
for c in "${shared_caches[@]}"; do
    if [[ -e "$c/$name" ]]; then
        info "NOTE: $name is already in $c; rsync below will skip it. Compare sha256 first."
    fi
done
echo
echo "Copy into the shared cache yourself (never overwrites an existing image):"
echo "  rsync -av --ignore-existing $final \"\$NXF_SINGULARITY_CACHEDIR/\""
