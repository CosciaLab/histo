#!/usr/bin/env bash
#
# Build an Apptainer SIF from a Docker image, named for Nextflow's singularity cache.
#
# Usage (from the repo root, on the cluster):
#   sbatch tools/build_sif.sbatch [--name FILE] [--force] [--need-gb N] <source> [out_dir]
#   bash tools/build_sif.sbatch --help
#
#   <source>   a registry ref, e.g. docker.io/josenimo/nimbus:0.0.5 (docker:// optional),
#              or a local docker-save tar, OCI archive, or OCI layout directory (no network).
#   out_dir    default /fast/AG_Coscia/$USER/sif. Never NXF_SINGULARITY_CACHEDIR: copy in yourself.
#   --name     output file name. Default for a ref: Nextflow's cache name, e.g.
#              docker.io-josenimo-nimbus-0.0.5.img. Required for a local source.
#   --force    replace an existing file in out_dir.
#   --need-gb  free space to require (default 60 for a ref, 4x the source size for a file).
#
# The output is a SIF either way; `.img` is only the name Nextflow looks for.
# Log: build_sif.<jobid>.log in the submit directory. Tests set BUILD_SIF_ATTEMPTS and
# BUILD_SIF_RETRY_SLEEP (default 4 attempts, 60 s doubling).

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
# Submit directory: SLURM does not create log directories, and this one always exists.
#SBATCH --output=build_sif.%j.log
#SBATCH --error=build_sif.%j.log

set -euo pipefail
# Colleagues read the copy in the shared cache; rsync -a keeps these permissions.
umask 022

usage() { sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
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
    printf '%s%s' "$(cd "$p" && pwd -P)" "$rest"
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
fast_base="/fast/AG_Coscia/${USER:?USER is not set}"
out_dir="${positional[1]:-$fast_base/sif}"
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

# Not /tmp: it is small and shared on login and compute nodes.
under_tmp() { [[ "$1" == /tmp || "$1" == /tmp/* ]]; }
tmp_base="${TMPDIR:-}"
if [[ -z "$tmp_base" ]] || under_tmp "$tmp_base"; then tmp_base="$fast_base/tmp"; fi
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$fast_base/apptainer_cache}"
if under_tmp "$APPTAINER_CACHEDIR"; then export APPTAINER_CACHEDIR="$fast_base/apptainer_cache"; fi

out_dir="$(resolve "$out_dir")"
tmp_base="$(resolve "$tmp_base")"
APPTAINER_CACHEDIR="$(resolve "$APPTAINER_CACHEDIR")"

# Shared cache: colleagues' running jobs read it, so this script never writes there.
nxf_cache=""
if [[ -n "${NXF_SINGULARITY_CACHEDIR:-}" ]]; then nxf_cache="$(resolve "$NXF_SINGULARITY_CACHEDIR")"; fi
for d in "$out_dir" "$tmp_base" "$APPTAINER_CACHEDIR"; do
    if [[ -n "$nxf_cache" && ("$d" == "$nxf_cache" || "$d" == "$nxf_cache"/*) ]]; then
        die "$d is inside NXF_SINGULARITY_CACHEDIR ($nxf_cache)" \
            "build elsewhere (default $fast_base/sif) and copy in with rsync --ignore-existing"
    fi
done

final="$out_dir/$name"
partial="$out_dir/$name.partial.$job_id"
job_tmp="$tmp_base/build_sif.$job_id"
export APPTAINER_TMPDIR="$job_tmp"

if [[ -e "$final" && "$force" -eq 0 ]]; then
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
info "output:      $final"
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

[[ ! -e "$final" || "$force" -eq 1 ]] || die "$final appeared during the build" "check for a parallel job; rerun with --force"
mv -f -- "$partial" "$final"

stage "Done"
info "file:     $final"
info "size:     $(du -h -- "$final" | cut -f1) ($(wc -c <"$final" | tr -d ' ') bytes)"
info "sha256:   $(sha256 "$final" | cut -d' ' -f1)"
info "format:   SIF (the .img suffix is only Nextflow's cache naming)"
if [[ -n "$nxf_cache" && -e "$nxf_cache/$name" ]]; then
    info "NOTE: $name is already in the shared cache; rsync below will skip it. Compare sha256 first."
fi
echo
echo "Copy into the shared cache yourself (never overwrites an existing image):"
echo "  rsync -av --ignore-existing $final \"\$NXF_SINGULARITY_CACHEDIR/\""
