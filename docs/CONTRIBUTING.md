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

`-stub` is the only loop that works on an Apple Silicon laptop, since the containers are amd64
only. Update a module's `stub:` block in the same commit as its outputs; the `stub-drift` hook
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

## Use of AI and LLMs

Humans remain responsible for the code regardless of the tools used.

- Keep commits small, single-concern and briefly described.
- Avoid unrelated changes, including refactors.
- Review and understand all generated code before committing. An earlier version of this
  pipeline had an AI-written TMA step that silently fabricated data on failure, and nobody read it.

See the nf-core [statement on AI](https://nf-co.re/blog/2026/statement-on-ai).
