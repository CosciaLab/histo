# cpsam_v2 and Segmentation Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cellpose defaults to `cpsam_v2` from a new image, and a SLURM-array benchmark scores
168 preprocessing settings against manual masks, ending in a ~13-slide `.pptx`.

**Architecture:** Part A bumps every sopa module to `josenimo/sopa:2.3.0-1` (2.3.0 plus baked
`cpsam_v2`), defaults `pretrained_model`, and guards against missing weights. Part B is a
package `tools/segmentation_benchmark/`: `prepare` (Mac) normalises three datasets to one crop
layout, `run` (cluster, in the image) does one setting per array task, `report` (Mac) makes
tables, figures and montages for the deck.

**Tech Stack:** Python (numpy, scipy, scikit-image, tifffile, pandas, matplotlib, roifile),
pytest via `uv run --frozen --group dev pytest tests/unit`, sopa 2.3.0, cellpose 4.2.1.1,
Docker buildx, SLURM + Apptainer, Nextflow/nf-test for Part A.

**Spec:** `docs/superpowers/specs/2026-11-07-segmentation-benchmark-design.md`. Read it first.

## Global Constraints

- Read CLAUDE.md. Branch `feat/segmentation-benchmark`; never `git push`. Commit titles under
  ~60 chars, ending with the `Co-Authored-By` line. Small single-concern commits.
- Pushing `docker.io/josenimo/sopa:2.3.0-1` to Docker Hub is cleared. Never run `sbatch`/`srun`;
  write the command, the user submits. Never touch `NXF_SINGULARITY_CACHEDIR`.
- Data lives outside the repo, in `$BENCH = /Users/jnimoca/Jose_BI/3_Projects/Segmentation_Benchmark`
  (Mac) and the user's cluster scratch. Never commit images, masks or results.
- Model: `cpsam_v2`, `diameter=30`, no rescaling. Cell plane = every non-DNA channel.
- Today's defaults: `max`, low percentile 1, high 99.9, `projection_sigma` 1, `gaussian_sigma` 1,
  `clip_limit` 0.2, flow 2, cellprob −6.
- Array layout, fixed: indices 0–143 cells on raw-channel datasets, 144–155 cells on TissueNet,
  156–167 nuclei on all datasets.
- IoU thresholds `(0.5, 0.6, 0.7, 0.8, 0.9)`; F1 at 0.5 is primary; per-threshold
  `ap = tp / (tp + fp + fn)` (cellpose's definition), matching at `iou >= t`.
- Scoring is our own ~30 lines of numpy, not `cellpose.metrics`: it keeps cellpose and torch
  out of the test environment. At IoU ≥ 0.5 matches are unique, so no Hungarian step is needed.

## Review Focus

1. A crop with no true or no predicted objects: F1 is 0 when only one side is empty, NaN when
   both are, and NaN crops are counted, not averaged. Test in Task 4.
2. A marker that is flat in a crop (`percentile_bounds` returns None) is left out, as in the
   pipeline; if every cell marker is flat, the cell plane is zeros, not a crash. Test in Task 6.
3. A resubmitted array task: an existing `results/N.csv` skips the task; a stale `N.csv.tmp` is
   overwritten. Test in Task 8.
4. ImageJ ROI types other than polygon/freehand (oval, rectangle, composite) rasterise or fail
   naming the crop and type; overlaps are logged per crop. Test in Task 7.
5. The Tonsil DNA channel: chosen as the channel brightest inside `GT_nuclei`, asserted to be
   the last (DAPI); a mismatch fails. Test in Task 7.

---

## Part A: cpsam_v2 in the pipeline

### Task 1: Build and push `josenimo/sopa:2.3.0-1`

**Files:**

- Create: `/Users/jnimoca/Jose_BI/2_Infrastructure/PY47_test_SOPA/docker/Dockerfile.2.3.0-1`
  (outside the repo; not committed)

**Produces:** image `docker.io/josenimo/sopa:2.3.0-1`, linux/amd64, with
`/opt/cellpose_models/cpsam_v2`.

- [ ] **Step 1:** Download `https://huggingface.co/mouseland/cellpose-sam/resolve/main/cpsam_v2`
      to the scratchpad; record its `sha256`.
- [ ] **Step 2:** Write the Dockerfile: `FROM docker.io/josenimo/sopa:2.3.0`, `curl` the file
      into `${CELLPOSE_LOCAL_MODELS_PATH}/cpsam_v2`, `sha256sum -c` against the recorded hash,
      `chmod a+r`. Header comment: why it exists, one line. If the base lacks `curl`, use
      `python -c "urllib.request.urlretrieve(...)"`.
- [ ] **Step 3:** `docker buildx build --platform linux/amd64 -t docker.io/josenimo/sopa:2.3.0-1 -f docker/Dockerfile.2.3.0-1 --load docker/`
- [ ] **Step 4: Verify offline.**
      `docker run --rm --platform linux/amd64 --network none docker.io/josenimo/sopa:2.3.0-1 python -c "from cellpose import models; m = models.CellposeModel(pretrained_model='cpsam_v2'); print(m.pretrained_model)"`
      Expected: prints `/opt/cellpose_models/cpsam_v2`, no "Downloading", no "not found" warning.
      Also `pip list` diff against 2.3.0 is empty.
- [ ] **Step 5:** `docker push docker.io/josenimo/sopa:2.3.0-1`; report the digest to the user.

### Task 2: Move modules to `sopa:2.3.0-1`

**Files:**

- Modify: `container` line in `modules/local/{aggregate,link_compartments,resolve,segment_patch,write_segmentations}/main.nf`
- Modify: `containers.tsv` (regenerated), `docs/CONTRIBUTING.md:158`

- [ ] **Step 1:** Replace `josenimo/sopa:2.3.0"` with `josenimo/sopa:2.3.0-1"` in the five modules.
- [ ] **Step 2:** `tools/container_manifest.py`, then `tools/container_manifest.py --check`. Expected: exit 0.
- [ ] **Step 3:** CONTRIBUTING line 158: name `2.3.0-1` and that it adds `cpsam_v2`.
- [ ] **Step 4:** `prek run --all-files` and `nf-core pipelines lint`. Expected: pass.
- [ ] **Step 5:** Commit `Bump sopa image to 2.3.0-1 (cpsam_v2 weights)`.

### Task 3: Default `cpsam_v2`, fail on missing weights

**Files:**

- Modify: `bin/segment_patch.py` (`METHOD_DEFAULTS`, new `check_weights`, call in `main`)
- Modify: `nextflow.config:71`, `nextflow_schema.json` (`pretrained_model`), `CHANGELOG.md`,
  `docs/decisions.md` (the "Cellpose-SAM replaced Cellpose 3" paragraph)
- Test: `tests/unit/test_segment_patch.py`

**Produces:** `check_weights(pretrained_model: str | None, models_dir: str | None) -> None`.

- [ ] **Step 1: Failing tests** in `tests/unit/test_segment_patch.py`:

```python
def test_cellpose_defaults_to_cpsam_v2():
    assert method_arguments({"method": "cellpose"})["pretrained_model"] == "cpsam_v2"

def test_missing_weights_name_the_model(tmp_path):
    with pytest.raises(ValueError, match=r"pretrained_model 'cpsam_v2' has no weights in .*CELLPOSE_LOCAL_MODELS_PATH"):
        check_weights("cpsam_v2", str(tmp_path))

def test_weights_present_or_path_pass(tmp_path):
    (tmp_path / "cpsam_v2").write_bytes(b"x")
    check_weights("cpsam_v2", str(tmp_path))
    check_weights(str(tmp_path / "cpsam_v2"), None)  # an existing path needs no models dir

def test_unset_models_dir_fails_for_a_name():
    with pytest.raises(ValueError, match="CELLPOSE_LOCAL_MODELS_PATH is not set"):
        check_weights("cpsam_v2", None)
```

- [ ] **Step 2:** `uv run --frozen --group dev pytest tests/unit/test_segment_patch.py -v`. Expected: 4 new FAIL.
- [ ] **Step 3:** Implement. `check_weights`: an existing path passes; otherwise the name must be a
      file in `models_dir`. `main` calls it for cellpose with
      `os.environ.get("CELLPOSE_LOCAL_MODELS_PATH")` before building the method. One-line "why"
      comment: cellpose silently loads its default for an unknown name, then downloads.
      `METHOD_DEFAULTS["cellpose"]["pretrained_model"] = "cpsam_v2"`, comment noting it is ours,
      not sopa's.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** `nextflow.config`: `pretrained_model = 'cpsam_v2'`. Schema: add
      `"default": "cpsam_v2"`, description "Cellpose weights: a name baked into the image
      (`cpsam_v2`, `cpsam`) or a path". Let prek regenerate the params templates.
- [ ] **Step 6:** `nf-test test --tag stub,validation`. If a snapshot changes only by
      `pretrained_model: cpsam_v2` in a spec, regenerate with `--update-snapshot` and check the diff
      shows nothing else.
- [ ] **Step 7:** CHANGELOG: new `## Unreleased` section above v3.0.0 (the tag exists): "Cellpose
      uses `cpsam_v2` (cellpose's own default); cell counts shift. `pretrained_model: cpsam` restores
      the old model." `decisions.md`: one sentence after the Cellpose-SAM paragraph: `cpsam_v2` is the
      default, following the cellpose developers; not benchmarked against `cpsam`.
- [ ] **Step 8:** prek, lint, pytest. Commit `Default Cellpose to cpsam_v2; fail on missing weights`.

## Part B: the benchmark

Package `tools/segmentation_benchmark/` (with `__init__.py`); tests in
`tests/unit/test_segmentation_benchmark.py`, importing `segmentation_benchmark.<module>`
(conftest puts `tools/` on the path). Scripts that run as CLIs insert `bin/` on `sys.path`, as
`tools/benchmark_projection.py` does.

### Task 4: Scoring

**Files:** Create `tools/segmentation_benchmark/{__init__,scoring}.py`

**Produces:** `IOU_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)`;
`score(true: np.ndarray, pred: np.ndarray) -> dict` with keys `n_true, n_pred, tp, fp, fn, f1,
ap_50, ap_60, ap_70, ap_80, ap_90, mean_ap` (`tp/fp/fn` at 0.5).

- [ ] **Step 1: Failing tests:**

```python
def square(labels, value, y, x, size=10):
    labels[y:y + size, x:x + size] = value

def test_identical_masks_score_one():
    t = np.zeros((50, 50), int); square(t, 1, 0, 0); square(t, 2, 20, 20)
    s = score(t, t.copy())
    assert (s["tp"], s["fp"], s["fn"], s["f1"], s["mean_ap"]) == (2, 0, 0, 1.0, 1.0)

def test_shifted_object_counts_by_iou():
    t = np.zeros((50, 50), int); square(t, 1, 0, 0)
    p = np.zeros_like(t); square(p, 7, 0, 2)          # IoU 80/120 = 0.667, labels need not match
    s = score(t, p)
    assert s["tp"] == 1 and s["ap_60"] == 1.0 and s["ap_70"] == 0.0

def test_one_side_empty_is_zero_both_empty_is_nan():
    t = np.zeros((50, 50), int); square(t, 1, 0, 0)
    assert score(t, np.zeros_like(t))["f1"] == 0.0
    assert np.isnan(score(np.zeros_like(t), np.zeros_like(t))["f1"])

def test_split_cell_is_one_fn_two_fp():
    t = np.zeros((50, 50), int); square(t, 1, 0, 0, 20)
    p = np.zeros_like(t); p[0:20, 0:10] = 1; p[0:20, 10:20] = 2
    s = score(t, p)
    assert (s["tp"], s["fp"], s["fn"]) == (0, 2, 1)
```

- [ ] **Step 2:** Run; expect import FAIL.
- [ ] **Step 3:** Implement with overlap counts from `np.unique` over `(true, pred)` pixel pairs
      (both > 0), object areas from `np.bincount`; `iou = inter / (area_t + area_p - inter)`; at
      each threshold `tp = (iou >= t).sum()`. `f1 = 2tp / (2tp + fp + fn)`, NaN when the denominator
      is 0.
- [ ] **Step 4:** Pass. **Step 5:** Commit `Benchmark: score masks by IoU matching`.

### Task 5: Settings

**Files:** Create `tools/segmentation_benchmark/settings.py`, `tools/segmentation_benchmark/settings.csv` (generated, committed)

**Produces:** `TODAY: dict`; `build_settings() -> pd.DataFrame` with columns `index, target
("cells"|"nuclei"), scope ("raw"|"tissuenet"|"all"), projection_method, low_percentile,
projection_sigma, gaussian_sigma, clip_limit, flow_threshold, cellprob_threshold`;
`today_index(settings, target, scope) -> int`. CLI: `python settings.py --out settings.csv`.

- [ ] **Step 1: Failing tests:**

```python
def test_layout():
    s = build_settings()
    assert len(s) == 168 and list(s["index"]) == list(range(168))
    assert (s[:144]["scope"] == "raw").all() and (s[144:156]["scope"] == "tissuenet").all()
    assert (s[156:]["target"] == "nuclei").all() and (s[156:]["scope"] == "all").all()

def test_today_is_in_every_block():
    s = build_settings()
    for target, scope in [("cells", "raw"), ("cells", "tissuenet"), ("nuclei", "all")]:
        row = s.loc[today_index(s, target, scope)]
        assert (row["gaussian_sigma"], row["clip_limit"], row["flow_threshold"]) == (1, 0.2, 2)

def test_committed_csv_matches(tmp_path):
    committed = pd.read_csv(Path(settings.__file__).with_name("settings.csv"))
    pd.testing.assert_frame_equal(committed, build_settings(), check_dtype=False)
```

- [ ] **Step 2–4:** Fail, implement with `itertools.product` over the spec's levels (raw block in
      the spec's factor order), pass. TissueNet and nuclei rows carry `TODAY`'s projection values
      (nuclei use them to build the nuclear plane; TissueNet ignores them).
- [ ] **Step 5:** Generate the CSV; commit `Benchmark: settings grid (168 array tasks)`.

### Task 6: Preprocessing

**Files:** Create `tools/segmentation_benchmark/preprocess.py`

**Consumes:** `percentile_bounds`, `rescale`, `combine` from `bin/project_channels.py`.

**Produces:**

- `project(image: np.ndarray, nuclear: int, method: str, low: float, sigma: float, high: float = 99.9) -> np.ndarray`:
  (2, Y, X) uint16, order `[cell, nuclear]`, the pipeline's order (rescale, Gaussian per channel,
  combine, `* 65535 + 0.5`).
- `sopa_preprocess(image: np.ndarray, gaussian_sigma: float, clip_limit: float) -> np.ndarray`:
  moved from `tools/benchmark_projection.py`, which then imports it.
- `pad_to(image: np.ndarray, size: int = 256) -> tuple[np.ndarray, tuple[int, int]]` (reflect,
  bottom/right) and `unpad(labels, shape) -> np.ndarray` (crop, `relabel_sequential`).

- [ ] **Step 1: Failing tests:**
  - `test_project_matches_pipeline`: build a one-level store as `tests/unit/test_project_channels.py`'s
    `store` fixture does (under 2000 px, no tissue mask, so the pipeline's percentiles come from
    the full image), run `project_channels.project`, read `<img>_projected`, and
    `np.testing.assert_array_equal` against `project(...)` on the same array.
  - `test_flat_marker_left_out_all_flat_gives_zeros`: one flat cell marker changes nothing
    against the same image without it; all flat gives a zero cell plane.
  - `test_pad_round_trip`: a 100×100 image pads to 256×256; `unpad` returns 100×100 labels
    numbered 1..n.
- [ ] **Step 2–4:** Fail, implement, pass. Run `pytest tests/unit` in full (benchmark_projection
      now imports from here).
- [ ] **Step 5:** Commit `Benchmark: pipeline-equal projection and padding`.

### Task 7: `prepare`

**Files:** Create `tools/segmentation_benchmark/prepare.py`; modify `pyproject.toml` (add
`roifile` to `dev`, with a one-line reason), `uv.lock`

**Produces:** under `--out`, `crops/<dataset>/<crop>/{image,cells,nuclei}.tif` (image C,Y,X as
stored; labels uint32) and `crops.csv` with columns `dataset, crop, platform, tissue,
pixel_size_um, channels ("|"-joined), nuclear (int), height, width, montage (bool)`. Functions:
`rois_to_labels(rois: list, shape: tuple[int, int]) -> tuple[np.ndarray, float]` (labels,
overlap share); `tonsil_nuclear_channel(image, nuclei) -> int`; one reader per dataset:
`read_crossplatform(root) / read_tonsil(root) / read_tissuenet(npz)`, each yielding
`(row: dict, image, cells, nuclei)`.

- [ ] **Step 1: Fetch** (user steps where tokens are needed; document in the README, Task 8):
      Tonsil via the Zenodo API (no token); Cross-platform with
      `uvx --from synapseclient synapse get -r syn27624812 --downloadLocation $BENCH/raw/crossplatform`
      (`SYNAPSE_AUTH_TOKEN`); TissueNet 1.1 zip downloaded by the user from datasets.deepcell.org.
- [ ] **Step 2: Inspect, then write findings into the module docstring:** Cross-platform crop
      TIFF axes, dtype and whether channel names are in its metadata or only in
      `Annotation Panel Table.xlsx` (if only there, add `openpyxl` to `dev`); which index is DAPI;
      ROI types present. TissueNet test npz: confirm `X` is (N, 256, 256, 2) = (nuclear, membrane)
      and which `y` channel is whole-cell, by comparing foreground areas; read `meta` for
      platform/tissue. Pixel size: 0.5 µm/px for TissueNet, Table 2 of the paper for Cross-platform,
      "unknown" for Tonsil.
- [ ] **Step 3: Failing tests:**
  - `test_polygon_rois_rasterise`: two `roifile.ImagejRoi.frompoints` squares → labels 1, 2 with
    the expected areas; overlap 0.
  - `test_overlap_goes_to_later_roi_and_is_reported`: two overlapping squares → overlap share > 0,
    overlapped pixels labelled 2.
  - `test_unsupported_roi_names_type`: an ROI whose type cannot be rasterised raises naming it.
  - `test_tonsil_dna_is_brightest_in_nuclei`: synthetic 3-channel image, channel 2 bright inside a
    nuclear mask → 2.
- [ ] **Step 4–5:** Implement (rasterise with `skimage.draw.polygon` on `roi.coordinates()`;
      `read_tonsil` asserts `tonsil_nuclear_channel == 6`); pass.
- [ ] **Step 6: Run** `uv run --frozen --group dev python tools/segmentation_benchmark/prepare.py --raw $BENCH/raw --out $BENCH/data`.
      Report per dataset: crops, true cells, max overlap share. Montage crops: the first crop by name
      of each Cross-platform platform (3), the first two Tonsil crops, the first TissueNet crop.
- [ ] **Step 7:** Commit `Benchmark: prepare datasets into one crop layout`.

### Task 8: `run`, the SLURM script and the README

**Files:** Create `tools/segmentation_benchmark/run.py`, `run_array.sbatch`, `README.md`

**Consumes:** Tasks 4–7.

**Produces:** `run.py --data DIR --setting-index N --out DIR [--gpu] [--limit-crops K] [--dataset NAME]`
writes `results/N.csv`: one row per crop, columns `index, target, dataset, crop, platform` +
`score()` keys + `seconds`; labels for montage crops to `labels/N/<dataset>__<crop>.tif`.

- [ ] **Step 1: Failing tests** (segmentation stubbed by monkeypatching `run.segment` to return
      the true labels):
  - `test_skips_existing_result`: an existing `results/3.csv` → returns without calling `segment`.
  - `test_overwrites_stale_tmp_and_writes_atomically`: a stale `3.csv.tmp` → final `3.csv` has one
    row per crop, F1 1.0; no `.tmp` left.
  - `test_scope_selects_crops`: a `tissuenet`-scope setting reads only TissueNet crops; `raw`
    excludes them.
- [ ] **Step 2–4:** Implement. `segment(image, channels, setting, gpu) -> labels` builds
      `sopa.segmentation.methods.cellpose_patch(diameter=30, channels=..., pretrained_model="cpsam_v2",
flow_threshold=..., cellprob_threshold=..., gpu=gpu)` once per task and calls it per crop.
      Cells on raw data: `project` → `sopa_preprocess` → segment `["cell", "nuclear"]`. TissueNet:
      the stored (membrane, nuclear) planes, rescaled to uint16, no projection. Nuclei: the projected
      nuclear plane only (TissueNet: its nuclear plane), `["nuclear"]`. Pad crops under 256 px. Pass.
- [ ] **Step 5: `run_array.sbatch`:** `--array=0-167%8`, `--gres=gpu:a40:1`, `--constraint=ceph`
      (as `conf/mdc.config`), `--cpus-per-task=8`, `--mem=32G`, `--time` left as `TIME` placeholder
      for the timing job to set, logs to `logs/%A_%a.out`. Body:
      `apptainer exec --nv "$SIF" python tools/segmentation_benchmark/run.py --data "$DATA" --setting-index "$SLURM_ARRAY_TASK_ID" --out "$OUT" --gpu`,
      with `SIF`, `DATA`, `OUT` required environment variables (fail if unset).
- [ ] **Step 6: Container smoke test (Mac, one tiny crop):**
      `docker run --rm --platform linux/amd64 --network none -v $PWD:/repo -v $BENCH/data:/data -w /repo docker.io/josenimo/sopa:2.3.0-1 python tools/segmentation_benchmark/run.py --data /data --setting-index <today raw> --out /tmp/out --dataset tonsil --limit-crops 1`
      Expected: one row, F1 > 0.
- [ ] **Step 7: README** (~40 lines): the three steps with commands, data layout, tokens, the
      timing job (`--array=<today raw>` with `--limit-crops 20`), then the full array, then rsync
      back. Commit `Benchmark: run one setting per SLURM array task`.

### Task 9: Cluster runs (user submits) — gate

- [ ] **Step 1:** Give the user: rsync of `$BENCH/data` and the repo to scratch; the image staging
      command from `docs/usage.md`; the timing `sbatch` command.
- [ ] **Step 2:** From the timing log, set `--time` (crops × seconds per crop × 1.5); commit.
- [ ] **Step 3:** The full-array command. When done, the user rsyncs `results/` and `labels/` to
      `$BENCH/results`. Check 168 result files; list missing indices for a resubmit.

### Task 10: `report`

**Files:** Create `tools/segmentation_benchmark/report.py`

**Produces:** in `--out`: `summary.csv` (per setting × dataset: mean and SD of F1 and mean AP,
n crops, n NaN crops), `effects_<factor>.png` (mean Cross-platform F1 per level, each factor
marginalised), `interaction.png` (heatmap of the two factors with the largest effect range),
`platforms.png` (best vs today per platform/dataset), `montage_<crop>.png` (today vs best,
outlines on the projection preview), `headline.json` (best and today's rows, F1 difference).

- [ ] **Step 1: Failing test** `test_summary_ranks_by_crossplatform_f1`: a fake `results/` of
      three settings where setting 2 is best on Cross-platform but worst on TissueNet →
      `headline.json` names 2.
- [ ] **Step 2–4:** Implement (matplotlib, read the dataviz skill first), pass.
- [ ] **Step 5:** Run on real results; look at every PNG. Commit `Benchmark: report tables and figures`.

### Task 11: The deck

- [ ] **Step 1:** Load the `anthropic-skills:pptx` skill. Build ~13 slides from Task 10's outputs
      only, in the spec's order, to `$BENCH/segmentation_benchmark.pptx`. Caveats slide: Tonsil's
      100 px crops and small cells, possible training overlap, crop vs slide percentiles, fixed
      diameter.
- [ ] **Step 2:** Render to images and check each slide by eye. Give the user the path.

Adoption (new defaults, `decisions.md` rewrite, ROADMAP) is a separate change after the user
reads the deck.
