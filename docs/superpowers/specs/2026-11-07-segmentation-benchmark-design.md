# cpsam_v2 and a ground-truth segmentation benchmark

ROADMAP 3.3 items 1 and 2. Resources (3.2) are out of scope.

## Goal

1. Cellpose segments with `cpsam_v2` by default. Not benchmarked against `cpsam`: we follow the
   cellpose developers.
2. Defaults for the steps before the model, chosen by whole-cell F1 against manual masks, run
   on the cluster GPUs. Results in a ~13-slide `.pptx`.

Success: the pipeline passes lint and stub tests on the new image; the array completes; the deck
names a recommended setting with its F1 against today's defaults.

## Part A: cpsam_v2 in the pipeline

- **Image** `docker.io/josenimo/sopa:2.3.0-1`: `FROM docker.io/josenimo/sopa:2.3.0` plus one layer
  that bakes `cpsam_v2` into `$CELLPOSE_LOCAL_MODELS_PATH` (`/opt/cellpose_models`). No pip
  re-resolve, so packages are identical. Dockerfile kept beside the 2.3.0 one in
  `2_Infrastructure/PY47_test_SOPA/docker/`. Built for `linux/amd64`, pushed to Docker Hub.
- **Default** `pretrained_model = 'cpsam_v2'` in `nextflow.config`, the schema and
  `bin/segment_patch.py`'s `METHOD_DEFAULTS`. A path still selects other weights.
- **Guard.** cellpose warns and loads its default for an unknown name, which then tries to
  download. `SEGMENT_PATCH` fails, naming the model, when a bare name has no file in
  `$CELLPOSE_LOCAL_MODELS_PATH`.
- Every module on `josenimo/sopa:2.3.0` moves to `2.3.0-1`; regenerate `containers.tsv`.
- CHANGELOG (default model changes, cell counts shift); one line in `decisions.md`.

## Part B: the benchmark

`tools/segmentation_benchmark/`, three steps. Data stays outside the repo (TissueNet is
non-commercial; sizes).

### Datasets

| Dataset                                                 | Role     | Crops            | Notes                                               |
| ------------------------------------------------------- | -------- | ---------------- | --------------------------------------------------- |
| Cross-platform mIF (Aleynick 2023, Synapse syn27624812) | decides  | ~160, 400–800 px | Vectra, Ultivue/Axioscan, CODEX; ImageJ ROI masks   |
| Tonsil mIF (Zenodo 22107836)                            | confirms | 10, 100 px       | 7 channels; paired cell/nucleus labels              |
| TissueNet 1.1, test split only                          | confirms | ~1,250, 256 px   | already 2-channel; cpsam trained on its train split |

### 1. `prepare` (Mac, network)

Download, then write one layout per crop: `image.tif` (C, Y, X), `cells.tif`, `nuclei.tif`
(uint32 instance labels), and one `crops.csv` (dataset, crop, platform, tissue, pixel size,
channel names, nuclear channel). ImageJ ROIs become labels; overlapping pixels go to the later
ROI and the overlap share is logged per crop. TissueNet and Synapse may need account tokens
from the user's environment. The user rsyncs the output to cluster scratch.

### 2. `run` (cluster GPU, in `sopa:2.3.0-1`, offline)

`run --setting-index N` reads row N of `settings.csv`, segments every applicable crop with
`cpsam_v2`, scores it, and writes `results/N.csv`: one row per crop. Written to a temp file,
then renamed; a task whose result exists exits at once, so resubmitting the array reruns only
failures. Labels are kept for 6 fixed montage crops only.

Preprocessing is the pipeline's code: `combine`, `percentile_bounds` and `rescale` from
`bin/project_channels.py`, then sopa's Gaussian, CLAHE and `cellpose_patch`, as
`tools/benchmark_projection.py` does now. Percentiles are taken on the crop (the pipeline uses
the whole slide). Cell channel: every non-DNA channel, as the default marker sheet. `diameter`
fixed at 30. Crops under 256 px are reflect-padded to 256 and cropped back.

### Settings

Cells, raw-channel datasets (144 settings):

| Factor                                   | Levels                          | Today |
| ---------------------------------------- | ------------------------------- | ----- |
| `projection_method`                      | max, mean                       | max   |
| `projection_low_percentile`              | 1, 50                           | 1     |
| `projection_sigma`                       | 0, 1, 2                         | 1     |
| `gaussian_sigma`                         | 0, 1, 2                         | 1     |
| `clip_limit`                             | 0, 0.2                          | 0.2   |
| (`flow_threshold`, `cellprob_threshold`) | (2, −6) sopa, (0.4, 0) Cellpose | sopa  |

The roadmap's "sum" is `mean` here: the pipeline offers max and mean, sum is mean times a
constant, and Cellpose normalises each image.
TissueNet gets the last three factors (12). Nuclei on the DNA channel, scored against nuclear
masks, get the same three (12). Array: 168 tasks, 1 GPU each.

### Scoring

cellpose `metrics.average_precision` per crop: F1 at IoU 0.5 (primary), mean AP over IoU
0.5–0.9, true and false positives, false negatives, predicted and true counts. Ranking: mean
F1 over Cross-platform crops, with its spread. Tonsil and TissueNet are reported beside it.

### 3. `report` (Mac)

From `results/*.csv`: `summary.csv` (per setting and dataset), one effect plot per factor, a
heatmap of the strongest pair, per-platform consistency, and montages of today's defaults
against the best setting. The deck is built only from these files.

Deck: title; question and `cpsam_v2`; datasets; method; grid; headline; factor effects;
interaction; consistency; thresholds; nuclei; montages and caveats; recommended defaults.

## Adoption

A later, separate commit after the user reads the deck: defaults in config and schema;
`decisions.md`'s benchmark paragraph rewritten, not appended to; CHANGELOG; ROADMAP 3.3 items
1–2 done.

## Tests

- pytest: ROI to labels on a toy ROI; scoring on hand-made label pairs with known F1;
  `settings.csv` row count; benchmark projection equals `bin/project_channels.py` on one input;
  the missing-weights guard.
- Image: `docker run` lists `cpsam_v2` and loads it. No segmentation on the Mac.
- Pipeline: prek, `nf-core pipelines lint`, stub nf-tests.
- Cluster: a one-task job timing one setting before the full array.

## User steps

Git push and PR; account tokens for downloads; rsync to scratch; submit `sbatch`; stage the new
image in the shared cache. The Docker Hub push of `2.3.0-1` is cleared for Claude.

## Risks

- Cross-platform may be in cpsam's training data; check the Cellpose-SAM paper before trusting
  it as held out.
- Tonsil's 100 px crops: border cells weigh heavily. Small cells (~11 px) against diameter 30.
- Crop percentiles differ from slide percentiles; the effect is reported, not removed.
