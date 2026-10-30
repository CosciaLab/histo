# Linux test environment for the laptop: unit, validation and stub tiers, as in CI.
# Native arm64 on Apple silicon. It runs no pipeline tool image (those are amd64; see CLAUDE.md 5).
FROM eclipse-temurin:21-jdk-jammy

ARG NXF_VER=25.10.4
ARG NFT_VER=0.9.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git procps rsync unzip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Pinned to the versions CI uses (.github/workflows/nf-test.yml).
RUN curl -fsSL https://get.nextflow.io | NXF_VER=${NXF_VER} bash \
    && mv nextflow /usr/local/bin/ && NXF_VER=${NXF_VER} nextflow -v \
    && curl -fsSL https://get.nf-test.com | bash -s ${NFT_VER} \
    && mv nf-test /usr/local/bin/

# Python env lives outside the mounted repo, built from the repo's own lockfile.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy NXF_VER=${NXF_VER} NXF_HOME=/opt/nxf-home
WORKDIR /opt/lock
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project --group dev

# The repo is mounted read-only at /repo and copied here, so a test run never writes to it.
COPY tools/test-container/entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]
