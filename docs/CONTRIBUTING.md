---
title: Contributing
---

# `CosciaLab/histo`: Contributing guidelines

A personal pipeline with one maintainer and no community contribution process. Report bugs as
a GitHub issue; contact the maintainer if you want to use it.

## Where the conventions live

- [`CLAUDE.md`](../CLAUDE.md): project context, priorities, module and container rules, testing,
  cluster rules for agents. Wins over generic nf-core defaults.
- [`AGENTS.md`](../AGENTS.md): nf-core agent guidelines, vendored verbatim.
- [`ROADMAP.md`](../ROADMAP.md): status and the tracker for open work. GitHub Issues is for bug reports.

## Testing

Four tiers, cheapest first. CI runs unit tests and `--tag stub,validation`; neither needs a
container. `tests/nextflow.config` caps tasks at 2 CPUs and 6 GB to fit the GitHub runner.

### Before committing

```bash
prek                                  # formatting, linting, custom guard hooks
nf-core pipelines lint                # nf-core conventions
pytest tests/unit                     # Python in bin/ and tools/
nf-test test --tag stub,validation    # what CI runs; exemplar tests are cluster-only
nextflow run . -profile test -stub --outdir results   # DAG and channel shapes, no containers
```

On an Apple Silicon laptop, `-stub` is the everyday loop; real runs work only for part of the
pipeline (see [On the Mac](#on-the-mac)). Update a module's `stub:` block in the same commit as its outputs; the `stub-drift` hook
checks this.

Do not hand-edit `nextflow_schema.json` (use `nf-core pipelines schema build`) or nf-test
snapshots (regenerate them).

### Unit tests (seconds)

Python logic in `bin/` and `tools/`: marker sheets, core naming, table relinking, QC metrics
and reports, container cache filenames.

```bash
pytest tests/unit
```

### Validation tests (seconds)

The input-rejecting functions, as `nextflow_function` tests. Most assert both the rejection
and the message wording; a check never watched to fail is not known to work.

```bash
nf-test test --tag validation
```

### Stub tests (seconds)

Channel topology only: wrong cycle grouping, lost core identity, a marker sheet reaching the
wrong sample, an unconsumed emit. Nothing about image quality.

```bash
nf-test test --tag stub
```

- `tests/stub_data/` holds tiny placeholders; stub runs only need inputs to exist.
- The tests use `-profile laptop`, which puts `tests/stub_bin` on `PATH`. `ashlar` and
  `backsub` declare versions with `eval()`, which runs even under `-stub`.
- `tests/default.nf.test` covers pre-stitched input (`-profile test`): `BASICPY`, `ASHLAR` and
  `SET_CHANNEL_NAMES` must not run, segmentation tiles into two patches, all three QC steps
  run. `nf-core pipelines lint` requires this file name.
- `tests/preprocessing_only.nf.test` runs the preprocessing half from a cycle samplesheet written
  at test time, and checks nothing after it runs.
- `tests/projection.nf.test` adds the channel projection before patching and drops it before
  `AGGREGATE`.
- `tests/instanseg.nf.test` runs the InstanSeg backend and its parameter checks.
- `tests/tma.nf.test` runs a dearrayed slide end to end: cores merge into one store, and
  `MERGE_REPORT` runs with `use_qc` and not without.

### Pre-release tests (cluster, by hand)

Real pixels through the whole chain. Not in CI: images are 8.8 GB (mIF) to 14.7 GB (with
Coreograph), against about 14 GB free on a GitHub runner.

|                | exemplar-001                        | exemplar-002                                                    |
| -------------- | ----------------------------------- | --------------------------------------------------------------- |
| covers         | mIF slide, whole-slide              | TMA, dearrayed                                                  |
| cycles         | 6, 7, 8: 12 channels                | 1, 2, 3: 12 acquired, 9 after subtraction                       |
| backsub        | no                                  | yes, real autofluorescence channels                             |
| also exercises | BaSiCPy, Ashlar, tiled segmentation | Coreograph, per-core subtraction, `remove`, merge, slide report |
| download       | 191 MB                              | 953 MB                                                          |

```bash
export HISTO_EXEMPLARS=/fast/AG_Coscia/$USER/HISTO/exemplars
bash tools/fetch_exemplars.sh

export TMPDIR=/fast/AG_Coscia/$USER/tmp && mkdir -p "$TMPDIR"
export NXF_TEMP="$TMPDIR" NXF_OPTS="-Djava.io.tmpdir=$TMPDIR" NXF_OFFLINE=true

nf-test test tests/exemplar001.nf.test --profile test_exemplar001,singularity,size_small,slurm
nf-test test tests/exemplar002.nf.test --profile test_exemplar002,singularity,size_small,slurm

uvx --from nf-core nf-core pipelines lint --release
```

If nf-test is blocked on the cluster, `nextflow run` with the same profiles and an `--outdir` is enough.

Gotchas:

- `--profile` replaces the test file's profile, so repeat it. Omitting it fails with
  `Missing required parameter(s): input`. `--profile=+...` appends instead.
- The temp variables are required: the login node's `/tmp` is small and shared, and overrunning
  it fails with `No space left on device`.

Data:

- `tools/fetch_exemplars.sh` pulls only the needed cycles from mcmicro's public S3 bucket and
  resumes interrupted downloads. Run it elsewhere and copy if the cluster has no internet.
- Marker sheets in `tests/exemplar_data/` are ours: mcmicro's lack `channel_role`, and
  exemplar-002's lacks `exposure` and `background`. Names, cycles and wavelengths match.
- Samplesheets are generated by the same script. nf-test gives each test a launch directory
  named by hash, so relative paths break and absolute ones are machine-specific.

Assertions are properties, not checksums: channel names, TMA core count, which processes ran
and how often, nuclear stain chosen by `channel_role`, subtraction blocks on every core,
background channels unchanged by subtraction, `versions.yml` complete. Cell counts must stay within ±2% of the
baselines in ROADMAP.

## Containers

This pipeline never pulls an image at run time. Every image is fetched in advance, on a machine with
working internet, and placed in the shared Singularity cache before any job is submitted.

That is not a preference. The cluster's connectivity is intermittent, and a pull that fails three
hours into a run wastes the run and the queue slot. A launch-time network dependency — including
resolving images through Wave — is treated as a defect.

### What the pipeline needs

[`containers.tsv`](../containers.tsv) at the repository root lists every image, one row per image
rather than per module, because several modules share one. It records the Singularity URI, the Docker
URI, the conda specification the image was built from, and which modules use it.

It is generated, not written:

```bash
tools/container_manifest.py            # rewrite it
tools/container_manifest.py --check    # fail if stale; the container-manifest prek hook
```

Regenerate it after adding or removing a module, or bumping a container.

**Five images are Docker-only.** `basicpy`, `coreograph` and `backsub` come from mcmicro and have no
BioContainers Singularity build. `ashlar` uses our own public `josenimo/ashlar` image, built from
the `Dockerfile` in [josenimo/ashlar](https://github.com/josenimo/ashlar) (branch `histo-qc`).
`josenimo/sopa:2.2.12` (InstanSeg, with cellpose 4 and the weights baked in) is also ours, built
from a Dockerfile kept outside this repository. Their
`singularity_uri` column is empty. They have to be converted from Docker rather than downloaded
directly, which is slower and subject to Docker Hub rate limiting. Budget for that.

### Building an image

Only when no suitable image exists. Start from a micromamba or conda-forge base, pin exact versions,
and build for the cluster's architecture rather than your laptop's:

```bash
docker buildx build --platform linux/amd64 -t ghcr.io/<user>/<tool>:<version> .
```

Building a SIF directly needs Linux with root or fakeroot, so it generally cannot be done on macOS.
Push to `ghcr.io` or `quay.io`, then fetch it back through the normal pre-staging route above so that
the cache holds exactly what the pipeline will ask for.

### On the Mac

The laptop is macOS on Apple Silicon. Docker Desktop runs the amd64 images under Rosetta, which
offers no AVX instructions. Checked on 2026-10-29:

- **Fail:** BaSiCPy (jaxlib refuses to start without AVX), Coreograph and StarDist (TensorFlow
  hangs on import).
- **Run:** Ashlar, backsub (which also has an arm64 build), sopa, Cellpose 3 (downloads its
  weights, so needs internet) and InstanSeg, under `-profile docker,emulate_amd64,laptop`.

So a real run on the Mac is possible only for the partial path: a stitched image, or tiles
with illumination profiles from a cluster run, then Cellpose or InstanSeg, without dearraying.
Expect small numerical differences (no AVX). The cluster is the reference.

## Metro map

`docs/images/pipeline_paths.svg` draws the three verified paths; variations are listed in
[output.md](output.md#what-runs).

The map is authored in [`pipeline_paths.mmd`](pipeline_paths.mmd) and rendered with
[nf-metro](https://github.com/seqeralabs/nf-metro):

```bash
pip install nf-metro==1.1.0   # 2.1.0 fails on this map; see ROADMAP
nf-metro validate docs/pipeline_paths.mmd
nf-metro render docs/pipeline_paths.mmd -o docs/images/pipeline_paths.svg
```

**Re-render this after any rewiring, and look at the result.** A change to the graph that leaves
the map stale is a change nobody has seen. The tests assert that processes ran and that their
outputs exist, which is not the same as checking what feeds what: sequencing `PUBLISH_SPATIALDATA`
behind `MERGE_SPATIALDATA` passed every test both before and after, and the map is where the
difference is visible. Reading it is a human step and deliberately not automated.

The station order was taken from `nextflow run . -stub -with-dag` exports of all three paths
rather than read off the source, so the map reflects the graph Nextflow actually built.
`nf-metro convert` turns such an export straight into a map, which is worth doing when the
pipeline changes shape.

Read a converted export rather than trusting it. Nextflow's DAG draws an edge per channel
consumer, so a channel that two processes read from produces edges to both even when one of them
discards part of the tuple: the WSI export shows `ASHLAR` reaching `QC_IMAGES`, which it does not,
because `subworkflows/local/qc/main.nf` drops the pre-subtraction image before `QC_IMAGES` sees
it.

nf-metro renders light only, so the figure keeps its own light surface on a dark page.

### What the map leaves out

One edge is deliberately absent. The pre-subtraction image also reaches `QC_METRICS`, which is
how the report compares channel statistics before and after subtraction. It exists whenever
`use_backsub` is set, on both the WSI and the TMA line: `COREOGRAPH` runs before `BACKSUB`, so a
dearrayed core is subtracted individually and its own unsubtracted twin is what QC compares it
against. Drawing this edge aborts nf-metro 1.1.0's renderer with a `CurveInvariantError`, so it
is described here instead.

For the same reason a second edge is absent: `ASHLAR` also sends its QC directory to
`QC_REPORT` (mIF and WSI lines) and to `MERGE_REPORT` (TMA line, per slide).

That ordering is the reason the TMA line lists `COREOGRAPH` before `BACKSUB`. The two orders
produce the same pixels, since subtraction has no whole-slide term, but subtracting first leaves
only a slide-sized before-image that cannot be paired with a core-sized store, and the
comparison then silently does not happen.

## Use of AI and LLMs

Humans remain responsible for the code regardless of the tools used.

- Keep commits small, single-concern and briefly described.
- Avoid unrelated changes, including refactors.
- Review and understand all generated code before committing. An earlier version of this
  pipeline had an AI-written TMA step that silently fabricated data on failure, and nobody read it.

See the nf-core [statement on AI](https://nf-co.re/blog/2026/statement-on-ai).
