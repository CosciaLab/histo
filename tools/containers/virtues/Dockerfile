# VirTues (bunnelab/virtues) with FlashAttention 2, sp32 weights, ESM-2 and UniProt baked in; no network at run time.
# Ubuntu 24.04 gives Python 3.12 like the sopa image (zarr 3.4 needs it); torch 2.5.1 from PyPI bundles CUDA 12.4.
FROM ubuntu:24.04

ARG VIRTUES_COMMIT=d2c25e1
ARG SPORA_IO_COMMIT=ef15868
# Passed by the build command (see README); the UniProt download below must report the same release.
ARG UNIPROT_RELEASE
ARG FLASH_ATTN_WHL=https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.5cxx11abiFALSE-cp312-cp312-linux_x86_64.whl

RUN apt-get update && apt-get install -y --no-install-recommends python3.12 python3.12-venv git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3.12 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1

# Data stack pinned to docker.io/josenimo/sopa:2.3.0 so both images read the same SpatialData store.
RUN pip install --no-cache-dir \
        numpy==2.5.4 pandas==3.1.1 pyarrow==26.0.1 zarr==3.4.2 dask==2026.8.0 xarray==2026.9.0 \
        shapely==2.1.2 geopandas==1.2.0 anndata==0.13.4 spatialdata==0.8.0

# Prebuilt wheel for this torch/CUDA/Python/ABI; FlashAttention is never compiled here.
RUN pip install --no-cache-dir --no-deps "${FLASH_ATTN_WHL}"

# Checkout also supplies assets/example_dataset (parity data) and configs. Editable, because upstream's
# packaging (include = ["virtues"]) omits subpackages from a regular install.
RUN git clone https://github.com/bunnelab/virtues /opt/virtues-src \
    && git -C /opt/virtues-src checkout "${VIRTUES_COMMIT}" && rm -rf /opt/virtues-src/.git

# --no-deps for the two packages: their pins target other torch builds; runtime imports are listed below.
RUN pip install --no-cache-dir --no-deps -e /opt/virtues-src \
        "git+https://github.com/bunnelab/spora-io@${SPORA_IO_COMMIT}" \
    && pip install --no-cache-dir \
        fair-esm==2.0.0 omegaconf==2.3.0 safetensors==0.7.0 einops==0.8.1 loguru==0.7.3 \
        scipy==1.16.3 tqdm==4.67.1 fastparquet==2026.9.0 huggingface_hub==2.4.0

ENV TORCH_HOME=/opt/torch
RUN python -c "import esm; esm.pretrained.esm2_t30_150M_UR50D()"

RUN python -c "import shutil; from huggingface_hub import hf_hub_download; \
p = hf_hub_download('bunnelab/virtues', 'virtues-sp32/model.safetensors', local_dir='/opt/virtues/dl'); \
shutil.move(p, '/opt/virtues/sp32.tmp')" \
    && mkdir -p /opt/virtues/sp32 && mv /opt/virtues/sp32.tmp /opt/virtues/sp32/model.safetensors && rm -rf /opt/virtues/dl

RUN test -n "${UNIPROT_RELEASE}" && mkdir -p /opt/uniprot && curl -fsSL -D /tmp/h.txt -o /opt/uniprot/human_sprot_isoforms.fasta \
    'https://rest.uniprot.org/uniprotkb/stream?format=fasta&includeIsoform=true&query=(organism_id:9606)+AND+(reviewed:true)' \
    && grep -i "^x-uniprot-release: ${UNIPROT_RELEASE}[[:space:]]*$" /tmp/h.txt && rm /tmp/h.txt

# After the UniProt layer so a rebuild reuses it: upstream's ESM module imports Bio; pytest runs the model tests.
RUN pip install --no-cache-dir biopython==1.88 pytest==9.2.0

ENV VIRTUES_WEIGHTS=/opt/virtues/sp32/model.safetensors \
    VIRTUES_UNIPROT=/opt/uniprot/human_sprot_isoforms.fasta \
    VIRTUES_UNIPROT_RELEASE=${UNIPROT_RELEASE} \
    VIRTUES_COMMIT=${VIRTUES_COMMIT} \
    VIRTUES_SRC=/opt/virtues-src \
    HF_HUB_OFFLINE=1

COPY check_image.py /opt/check_image.py
