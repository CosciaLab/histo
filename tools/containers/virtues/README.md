# VirTues image (docker.io/josenimo/virtues:d2c25e1)

[bunnelab/virtues](https://github.com/bunnelab/virtues) at `d2c25e1` and spora-io at `ef15868`, with
FlashAttention 2, the `sp32` weights, ESM-2 150M and human UniProt (reviewed, with isoforms) baked in,
so no run needs the network. `check_image.py` is at `/opt/check_image.py`.

- Build (`UNIPROT_RELEASE` must match what UniProt serves, or the build fails; ~20 min under emulation):
  `REL=$(curl -sI 'https://rest.uniprot.org/uniprotkb/stream?format=fasta&includeIsoform=true&query=(organism_id:9606)+AND+(reviewed:true)' | tr -d '\r' | awk -F': ' 'tolower($1)=="x-uniprot-release"{print $2}')`
  then `docker buildx build --platform linux/amd64 --build-arg UNIPROT_RELEASE=$REL --load -t docker.io/josenimo/virtues:d2c25e1 tools/containers/virtues`
- Mac check (offline, no CUDA): `docker run --rm --platform linux/amd64 --network none docker.io/josenimo/virtues:d2c25e1 python /opt/check_image.py --cpu-only`
- Save: `docker save docker.io/josenimo/virtues:d2c25e1 -o virtues_d2c25e1.tar`
- SIF on the cluster: `sbatch tools/build_sif.sbatch docker.io/josenimo/virtues:d2c25e1`, or from the tar with `--name docker.io-josenimo-virtues-d2c25e1.img virtues_d2c25e1.tar`
- Cluster check (GPU node, as an `sbatch` or interactive job; the example core is read from the image):
  `apptainer exec --nv --containall "$NXF_SINGULARITY_CACHEDIR/docker.io-josenimo-virtues-d2c25e1.img" python /opt/check_image.py`
  It imports `flash_attn`, runs `compute_cell_tokens` on the bundled example core as notebook 2 does,
  and prints the token shapes. Send the output back.

Environment (read by the pipeline): `VIRTUES_WEIGHTS`, `VIRTUES_UNIPROT`, `VIRTUES_UNIPROT_RELEASE`,
`VIRTUES_COMMIT`, `VIRTUES_SRC` (checkout with `assets/example_dataset`), `TORCH_HOME=/opt/torch`, `HF_HUB_OFFLINE=1`.

## Findings (2026-11-24)

- **Base.** Not `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`: it is Python 3.11, and the sopa
  image's `numpy 2.5` and `zarr 3.4` need 3.12. Now `ubuntu:24.04` (Python 3.12.3, venv) with
  `torch 2.5.1` and `torchvision 0.20.1` from PyPI (CUDA 12.4 libraries bundled), and the
  `flash_attn-2.7.4.post1+cu12torch2.5cxx11abiFALSE-cp312` wheel. Never compiled. Image is large (12.9 GB on disk).
- **Versions.** torch 2.5.1+cu124, FlashAttention 2.7.4.post1, spatialdata 0.8.0, anndata 0.13.4,
  geopandas 1.2.0, numpy 2.5.4, pandas 3.1.1, zarr 3.4.2 (same as `sopa:2.3.0`), fair-esm 2.0.0,
  safetensors 0.7.0, omegaconf 2.3.0, einops 0.8.1.
- **Editable install.** Upstream's `pyproject.toml` has `include = ["virtues"]`, so a normal install
  drops `virtues.modules`. The image installs `/opt/virtues-src` with `-e`.
- **flash_attn imports on CPU.** `virtues.modules.multiplex_virtues` imports and the weights load
  with `strict=True` (`All keys matched successfully`) on the Mac under emulation. No stub needed.
- **ESM-2 parity.** Our embedding of the 40 IDs in `assets/example_dataset/marker_embeddings/` against
  the bundled `.pt`: max abs difference 9.5e-07 for 39 of them (CPU float32 noise). One outlier,
  `P36402` (TCF7), 3.4e-02: UniProt 2026_04 has sequence version 4 (one residue differs from version
  3, release 2025_02). The version 3 sequence gives 1.5e-07. Isoform `P08575-8` matches.
- **Token shape (from the code, cluster to confirm).** `encoder_output.patch_summary_tokens` is a list
  with one `(16, 16, 512)` tensor per 128 px crop (`H W D`; dtype set by autocast, cluster prints it).
- **Backsub (0.5.1, `background_sub.py`).** Output dtype equals input dtype: `data_type` read from the
  source (L171), integer results clipped then `.astype(ref_dtype)` (L243-246). The `--marker-output` CSV
  keeps unknown columns such as `uniprot_id`: it reads the sheet with `pd.read_csv` (L378) and drops only
  `keep`, `ind`, `processed`, `factor`, `bg_idx` (L383-385; `remove` earlier, L118), adds `channel_number`
  (L386); rows with `remove` true are dropped (L380).
- **Cluster check.** Pending, run by the user.
