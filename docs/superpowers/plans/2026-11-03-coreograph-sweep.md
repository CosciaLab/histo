# Coreograph downsample sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before dearraying a TMA, detect cores at k = 3…7 without writing tiles, score each k
against the user's expected count and diameter, and run `COREOGRAPH` once with the best k.

**Architecture:** Two `bin/` scripts in the existing `unetcoreograph:2.4.6` image: detect
(one task per slide × k, imports Coreograph's UNet, copies its TMA-mode post-processing) and
select (one per slide). `PREPROCESS_IMAGES` fans out, groups, joins the chosen k into meta,
and `conf/modules.config` builds `COREOGRAPH`'s args from it. Setting `coreograph_args`
bypasses all of it.

**Tech Stack:** Nextflow DSL2, nf-test, Python 3 (numpy, scikit-image, tifffile, zarr,
matplotlib; TensorFlow only in the container), pytest via `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-03-coreograph-sweep-design.md`

## Global Constraints

- Work in the worktree `.claude/worktrees/coreograph-sweep`, branch `feat/coreograph-sweep`.
- Sweep factors are exactly `[3, 4, 5, 6, 7]`, a constant in the subworkflow, not a param.
- Sweep-mode Coreograph flags: `--channel 0 --buffer 2 --sensitivity 0.3`.
- Score = `count_error + diam_error + size_cv`; zero cores = infinity; tie → smaller k.
- Warn when the winner has `count_error > 0.1` or `diam_error > 0.25`. Never fail on a poor
  winner (but see Review Focus 1).
- Container image for both new modules: `docker.io/labsyspharm/unetcoreograph:2.4.6`. It has
  no pandas: use `csv`/`json` from the standard library.
- No `tifffile.imread`, `imageio.imread` or `skimage.io.imread` in `bin/` (prek hook
  `no-eager-image-reads`).
- Every local module: a `stub:` block and a versions topic entry (prek hooks).
- `nextflow_schema.json` may be edited by hand once Task 0 lands (hooks lint it). Never
  hand-edit `assets/params_template*.yml`.
- Commit titles under ~60 chars; one-line "why" comments; end commits with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- Mac cannot run the Coreograph image, but Coreograph runs natively in
  `/Users/jnimoca/Jose_BI/2_Infrastructure/PY46_coreograph_test/.venv-coreograph` (Task 2
  local check). The image itself is exercised on the cluster (Task 6).

## Review Focus

1. **Every k finds zero cores** (wrong channel, blank image). A reasonable user expects a clear
   stop at select, not an obscure `COREOGRAPH` failure. Select exits non-zero naming the
   slide and suggesting the channel or `coreograph_args`. Test in Task 3.
2. **Pixel size in a unit other than µm, or with no unit attribute** (OME default is µm).
   Convert nm/mm; reject anything else with a message. Test in Task 1.
3. **Single-channel (2D) OME-TIFF.** Coreograph handles it; the strided read must too.
   Test in Task 1.
4. **More than 255 cores.** The sweep's coremask stays `uint16` and `n_cores` counts past 255.
   Test in Task 2.
5. **Two slides in one run.** Each slide gets its own k; groups do not mix. Test in Task 5.

---

### Task 0: Allow agent schema edits, lint after each

**Files:**

- Modify: `CLAUDE.md` §3 (the "Never hand-edit `nextflow_schema.json`" line), the matching
  sentence in `docs/CONTRIBUTING.md` (~line 36)
- Create: `.claude/settings.json` (committed; `settings.local.json` stays personal)
- Create: `tools/lint_schema_hook.sh`
- Modify: `.pre-commit-config.yaml` (local hook `schema-lint`)

**Interfaces:**

- Produces: after any agent `Edit`/`Write` whose `tool_input.file_path` ends in
  `nextflow_schema.json`, `tools/lint_schema_hook.sh` runs
  `nf-core pipelines schema lint nextflow_schema.json`; on failure it prints the lint output
  to stderr and exits 2 (Claude Code feeds that back to the agent). Other files: exit 0
  silently. prek runs the same lint when `nextflow_schema.json` or `nextflow.config` changes.

- [ ] **Step 1: Check what `schema lint` catches.** In a scratch copy, add a param to
      `nextflow.config` only and run the lint. If it passes, the prek hook also runs
      `nf-core pipelines lint --dir . -k schema_params`; record which in the hook comment.
- [ ] **Step 2: Write the hook script and settings** (`PostToolUse`, matcher
      `Edit|Write|MultiEdit`, command `"$CLAUDE_PROJECT_DIR"/tools/lint_schema_hook.sh`).
      Use the `update-config` skill for the settings file.
- [ ] **Step 3: Verify both ways.** Pipe a fake hook payload naming `nextflow_schema.json`
      into the script with a deliberately broken copy (missing comma) → exit 2 and the error;
      restored → exit 0. A payload naming `README.md` → exit 0, no lint run.
      `prek run schema-lint --all-files` passes.
- [ ] **Step 4: Edit `CLAUDE.md` and `CONTRIBUTING`:** "Agents may edit
      `nextflow_schema.json` directly; a hook lints it after every edit and at commit."
- [ ] **Step 5: Commit** — `Allow agent schema edits, lint after each`

---

### Task 1: Lazy channel read, pixel size, metrics

**Files:**

- Create: `bin/coreograph_detect.py` (pure functions only in this task)
- Create: `tests/unit/test_coreograph_detect.py`
- Modify: `pyproject.toml` (dev group: add `scikit-image>=0.22`, `matplotlib>=3.8`, with a
  one-line comment that they mirror the Coreograph image)

**Interfaces:**

- Produces:
  - `read_downsampled(path: Path, channel: int, k: int) -> np.ndarray` — 2D, level 0 read via
    `tifffile.TiffFile(path).series[0].aszarr(level=0)` opened with `zarr.open(store, mode="r")`,
    then `[channel, ::2**k, ::2**k]` (or `[::2**k, ::2**k]` when 2D), cropped to
    `(H >> k, W >> k)`. Equals k nearest-neighbour halvings by `cv2.resize` (spec, Findings).
  - `pixel_size_um(path: Path) -> float` — `PhysicalSizeX` from `TiffFile(path).ome_metadata`
    parsed with `xml.etree.ElementTree`; unit default `µm`; `nm`/`mm` converted; missing
    size or other unit → `ValueError` whose message contains `"pixel size"`.
  - `core_metrics(labels: np.ndarray, est_core_diam_px: float, k: int, pixel_um: float, expected_cores: int, diameter_mm: float) -> dict`
    with keys `k, n_cores, count_error, diam_mm, diam_error, size_cv, crop_ratio, core_px_at_k, um_per_px`.
    Labels are at the downsampled scale. `diam_mm` = median of `2*sqrt(area/π)` × `2**k` ×
    `pixel_um` / 1000. `crop_ratio` = `est_core_diam_px * 2**k * pixel_um / 1000 / diameter_mm`.
    `core_px_at_k` = `diameter_mm * 1000 / pixel_um / 2**k`; `um_per_px` = `pixel_um * 2**k`.
    With zero labels, `diam_mm`,
    `diam_error`, `size_cv`, `crop_ratio` are `None`.
  - `centroids_full_res(labels: np.ndarray, k: int) -> np.ndarray` — regionprops centroids
    (y, x) × `2**k`, label order, matching Coreograph's `centroids / dsFactor`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_coreograph_detect.py`. Helper
      `write_ome(tmp_path, arr, physical_size=0.65, unit="µm")` writes with
      `tifffile.imwrite(..., ome=True, metadata={"PhysicalSizeX": ..., "PhysicalSizeXUnit": ...})`
      (omit keys when `None`). Helper `discs(centres, r, shape)` labels filled discs 1..n.

```python
def reference_halvings(a, k):
    for _ in range(k):
        a = a[::2, ::2][: a.shape[0] // 2, : a.shape[1] // 2]
    return a

@pytest.mark.parametrize("k", [0, 1, 3])
def test_read_downsampled_matches_repeated_halving_odd_shape(tmp_path, k):
    arr = np.arange(3 * 101 * 77, dtype=np.uint16).reshape(3, 101, 77)
    p = write_ome(tmp_path, arr)
    assert np.array_equal(read_downsampled(p, 1, k), reference_halvings(arr[1], k))

def test_read_downsampled_single_channel(tmp_path):            # Review Focus 3
    arr = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64)
    assert read_downsampled(write_ome(tmp_path, arr), 0, 2).shape == (16, 16)

def test_pixel_size_um(tmp_path):
    assert pixel_size_um(write_ome(tmp_path, ARR, 0.65)) == pytest.approx(0.65)

@pytest.mark.parametrize("value,unit,expected", [(650, "nm", 0.65), (0.00065, "mm", 0.65), (0.65, None, 0.65)])
def test_pixel_size_units(tmp_path, value, unit, expected):     # Review Focus 2
    assert pixel_size_um(write_ome(tmp_path, ARR, value, unit)) == pytest.approx(expected)

def test_pixel_size_missing_fails(tmp_path):
    with pytest.raises(ValueError, match="pixel size"):
        pixel_size_um(write_ome(tmp_path, ARR, None, None))

def test_metrics_four_discs():
    # k=2, 0.5 µm/px: radius 50 px at k → diameter 100 px × 4 × 0.5 µm = 0.2 mm
    labels = discs([(100, 100), (100, 300), (300, 100), (300, 300)], 50, (400, 400))
    m = core_metrics(labels, est_core_diam_px=120, k=2, pixel_um=0.5, expected_cores=4, diameter_mm=0.2)
    assert m["n_cores"] == 4 and m["count_error"] == 0
    assert m["diam_mm"] == pytest.approx(0.2, rel=0.02)
    assert m["diam_error"] < 0.02 and m["size_cv"] < 0.02
    assert m["crop_ratio"] == pytest.approx(1.2)
    assert m["core_px_at_k"] == pytest.approx(100)
    assert m["um_per_px"] == pytest.approx(2.0)

def test_metrics_merged_blob_raises_size_cv():
    labels = discs([(100, 100), (300, 100), (300, 300)], 50, (400, 400))
    labels[labels == 1] = 0
    labels[50:150, 50:350] = 1  # one blob spanning two core positions
    m = core_metrics(labels, 120, 2, 0.5, 4, 0.2)
    assert m["n_cores"] == 3 and m["count_error"] == pytest.approx(0.25)
    assert m["size_cv"] > 0.3

def test_metrics_zero_cores():
    m = core_metrics(np.zeros((50, 50), np.int32), 0, 3, 0.65, 4, 1.5)
    assert m["n_cores"] == 0 and m["count_error"] == 1
    assert m["diam_mm"] is None and m["size_cv"] is None

def test_centroids_scaled_to_full_res():
    labels = discs([(10, 20)], 3, (40, 40))
    assert np.allclose(centroids_full_res(labels, 3), [[80, 160]])
```

- [ ] **Step 2: Run, expect FAIL** (import error)
      Run: `uv run pytest tests/unit/test_coreograph_detect.py -v`
- [ ] **Step 3: Implement the four functions** in `bin/coreograph_detect.py`, with a
      `#!/usr/bin/env python3` shebang, a module docstring, and `chmod +x`.
- [ ] **Step 4: Run, expect PASS**; also `prek run --files bin/coreograph_detect.py`
      passes (ruff, eager-read hook).
- [ ] **Step 5: Commit** — `Add lazy read and metrics for Coreograph sweep`

---

### Task 2: Detection, CLI and COREOGRAPH_DETECT module

**Files:**

- Modify: `bin/coreograph_detect.py`
- Modify: `tests/unit/test_coreograph_detect.py`
- Create: `modules/local/coreograph_detect/main.nf`

**Interfaces:**

- Consumes: Task 1 functions.
- Produces:
  - `detect_labels(img: np.ndarray, sensitivity: float, buffer: float) -> tuple[np.ndarray, float]`
    → (core labels at the downsampled scale, Coreograph's `estCoreDiam` in downsampled px).
    Imports TensorFlow and Coreograph inside the function: `sys.path.insert(0, "/app")`,
    `from UNetCoreograph import getProbMaps`, then `classProbs = getProbMaps(img, 0, "/app/model")`.
    The body after that is `UNetCoreograph.py` 2.4.6 lines 1006–1027 and 1029–1039 copied
    verbatim (`preMask` … `coreLabel = watershed(...)`), with a header comment:
    `# Copied from HMS-IDAC/UNetCoreograph 2.4.6, UNetCoreograph.py L1006-1039 (MIT). Keep in sync on bumps.`
  - CLI: `coreograph_detect.py --image PATH --downsample-factor K --channel C --sensitivity S --buffer B --expected-cores N --core-diameter-mm D --prefix P`
  - `main(argv: list[str] | None = None) -> None` writes, in the working directory:
    `{P}_k{K}_metrics.json` (the `core_metrics` dict plus `pixel_um`), `{P}_k{K}_coremask.tif`
    (`uint16`, zlib), `{P}_k{K}_centroids.txt` (`np.savetxt(..., fmt="%10.5f")`, Coreograph's
    format), `{P}_k{K}_overlay.png` (label boundaries and numbers on the downsampled channel,
    longest side ≤ 1024 px, title `k=K: n cores`). A `ValueError` from Task 1 becomes
    `sys.exit(message)`.
  - Process `COREOGRAPH_DETECT`: input `tuple val(meta), path(image), val(k)`; outputs
    `tuple val(meta), path("*_k*_metrics.json"), path("*_k*_overlay.png"), emit: results`,
    `tuple val(meta), path("*_k*_coremask.tif"), path("*_k*_centroids.txt"), emit: labels`,
    and `tuple val("${task.process}"), val('coreograph'), val("2.4.6"), topic: versions`.
    Script exports `MPLCONFIGDIR=$PWD` and calls the CLI with `--downsample-factor ${k}`,
    `--prefix ${prefix}` and `${task.ext.args}`. Stub touches all four files for `k`, and the
    JSON contains `{"k": k, "n_cores": 2}`.

- [ ] **Step 1: Write failing tests** that monkeypatch `coreograph_detect.detect_labels` to
      return `(discs(...), 120.0)`, so `main` runs without TensorFlow:

```python
def test_main_writes_four_outputs(tmp_path, monkeypatch):
    img = write_ome(tmp_path, np.zeros((2, 512, 512), np.uint16), 0.65)
    monkeypatch.setattr(coreograph_detect, "detect_labels", lambda im, s, b: (discs(CENTRES, 10, im.shape), 30.0))
    monkeypatch.chdir(tmp_path)
    main(["--image", str(img), "--downsample-factor", "3", "--channel", "0", "--sensitivity", "0.3",
          "--buffer", "2", "--expected-cores", "4", "--core-diameter-mm", "1.5", "--prefix", "slide"])
    m = json.loads((tmp_path / "slide_k3_metrics.json").read_text())
    assert m["k"] == 3 and m["n_cores"] == 4 and m["pixel_um"] == pytest.approx(0.65)
    for suffix in ["coremask.tif", "centroids.txt", "overlay.png"]:
        assert (tmp_path / f"slide_k3_{suffix}").stat().st_size > 0

def test_coremask_keeps_labels_above_255(tmp_path, monkeypatch):   # Review Focus 4
    labels = np.zeros((120, 90), np.int32)
    for i, (y, x) in enumerate(itertools.product(range(0, 120, 6), range(0, 90, 6)), start=1):
        labels[y:y + 3, x:x + 3] = i  # 20 × 15 = 300 squares
    # detect_labels patched to return (labels, 3.0); main called as above
    assert tifffile.TiffFile(tmp_path / "slide_k3_coremask.tif").asarray().max() == 300
    assert json.loads((tmp_path / "slide_k3_metrics.json").read_text())["n_cores"] == 300

def test_main_exits_with_message_without_pixel_size(tmp_path, monkeypatch):
    # image written by write_ome(..., None, None); same argv as above
    with pytest.raises(SystemExit, match="pixel size"):
        main(ARGV)
```

`ARGV` is the argv list of the first test, as a module constant pointing at `tmp_path`'s image
via a fixture.

(Reading the written TIFF back with `TiffFile(...).asarray()` in tests is fine; the hook only
covers `bin/`.)

- [ ] **Step 2: Run, expect FAIL.** `uv run pytest tests/unit/test_coreograph_detect.py -v`
- [ ] **Step 3: Implement `detect_labels` and `main`; write the module.** Copy the Coreograph
      lines from the 2.4.6 tag
      (`https://raw.githubusercontent.com/HMS-IDAC/UNetCoreograph/2.4.6/UNetCoreograph.py`),
      changing only the variable names needed to bind `img` to `I`-scale input. Skip line 1028
      (a comment) and stop before line 1040 (`P = regionprops(coreLabel)`). Return
      `coreLabel.astype(np.int32), float(estCoreDiam)`.
- [ ] **Step 4: Run, expect PASS**; `prek run --files bin/coreograph_detect.py modules/local/coreograph_detect/main.nf`.
- [ ] **Step 4b: Native check against real Coreograph (local, not committed).** With
      `PY46=/Users/jnimoca/Jose_BI/2_Infrastructure/PY46_coreograph_test` and
      `IMG=$PY46/out/baseline/wsi_allcycles.ome.tif`, in a scratchpad directory:
      `$PY46/.venv-coreograph/bin/python $PY46/vendor/UNetCoreograph/UNetCoreograph.py --imagePath $IMG --outputPath ref --downsampleFactor 4 --channel 0 --buffer 2`,
      then run `bin/coreograph_detect.py` with the same venv (with `/app` replaced by
      `$PY46/vendor/UNetCoreograph` through an env var `COREOGRAPH_APP`, default `/app`) at
      k = 4, N = 4, D = 1.5. Expected: `diff ref/centroidsY-X.txt <prefix>_k4_centroids.txt`
      is empty. Then run k = 3…7 and select, and report the TSV to the user. If the venv is
      gone, say so and leave this to Task 6.
- [ ] **Step 5: Commit** — `Add COREOGRAPH_DETECT for the downsample sweep`

---

### Task 3: Selection and COREOGRAPH_SELECT module

**Files:**

- Create: `bin/coreograph_select.py`
- Create: `tests/unit/test_coreograph_select.py`
- Create: `modules/local/coreograph_select/main.nf`

**Interfaces:**

- Consumes: Task 2's `*_metrics.json` and `*_overlay.png`.
- Produces:
  - `score(m: dict) -> float`, `choose(metrics: list[dict]) -> dict` (min by `(score, k)`),
    `warning(m: dict) -> str | None`.
  - CLI: `coreograph_select.py --metrics F [F ...] --overlays F [F ...] --prefix P`.
  - `main(argv: list[str] | None = None) -> None` writes `{P}_sweep.tsv` (columns, in order:
    `k, um_per_px, n_cores, count_error, diam_mm, diam_error, size_cv, crop_ratio, core_px_at_k, score, selected, warning`,
    rows sorted by score then k), `{P}_sweep_overlays.png` (overlays in a row, ordered by k),
    and `{P}_selection.json` = `{"downsample_factor": int, "warning": str | null}`. Prints
    the warning to stderr. All scores infinite → `sys.exit` with a message naming the prefix,
    stating no factor detected any core, and suggesting checking the dearray channel or
    setting `coreograph_args`.
  - Process `COREOGRAPH_SELECT`: input `tuple val(meta), path(metrics), path(overlays)`;
    outputs `tuple val(meta), path("*_selection.json"), emit: selection`,
    `tuple val(meta), path("*_sweep.tsv"), path("*_sweep_overlays.png"), emit: report`, the
    versions topic as in Task 2. Stub writes `{"downsample_factor": 5, "warning": null}` and
    touches the TSV and PNG.

  This replaces the spec's `selected_k.txt`: prefixed so slides do not collide when published,
  and JSON so the warning travels with k.

- [ ] **Step 1: Write failing tests** with metric dicts built by a helper `m(k, n, ce, de, cv)`:

```python
def test_lowest_score_wins():
    assert choose([m(3, 6, .5, .4, .3), m(4, 4, 0, .05, .02), m(5, 4, 0, .3, .1)])["k"] == 4

def test_zero_cores_never_wins():
    assert score(m(7, 0, 1, None, None)) == math.inf
    assert choose([m(6, 0, 1, None, None), m(7, 9, 1.25, .9, .8)])["k"] == 7

def test_tie_goes_to_smaller_k():
    assert choose([m(5, 4, 0, .1, .1), m(4, 4, 0, .1, .1)])["k"] == 4

@pytest.mark.parametrize("ce,de,warns", [(0.1, 0.25, False), (0.11, 0, True), (0, 0.26, True)])
def test_warning_thresholds(ce, de, warns):
    assert (warning(m(4, 4, ce, de, 0)) is not None) == warns

def test_main_outputs(tmp_path, monkeypatch):
    # metrics JSONs for k = 3, 4, 5 (k = 4 best, no warning) and 8×8 PNGs; main with --prefix s
    assert json.loads((tmp_path / "s_selection.json").read_text()) == {"downsample_factor": 4, "warning": None}
    rows = list(csv.DictReader(open(tmp_path / "s_sweep.tsv"), delimiter="\t"))
    assert [r["k"] for r in rows][0] == "4" and rows[0]["selected"] == "true"
    assert (tmp_path / "s_sweep_overlays.png").stat().st_size > 0

def test_all_zero_cores_exits(tmp_path, monkeypatch):            # Review Focus 1
    # every metrics JSON has n_cores = 0
    with pytest.raises(SystemExit, match="no downsample factor detected any core"):
        main(["--metrics", *jsons, "--overlays", *pngs, "--prefix", "s"])
```

- [ ] **Step 2: Run, expect FAIL.** `uv run pytest tests/unit/test_coreograph_select.py -v`
- [ ] **Step 3: Implement the script (shebang, `chmod +x`, `csv`/`json` only) and the module.**
- [ ] **Step 4: Run, expect PASS**; `prek run --files` on the three files.
- [ ] **Step 5: Commit** — `Add COREOGRAPH_SELECT for the downsample sweep`

---

### Task 4: Parameters and validation

**Files:**

- Modify: `nextflow.config:27-29` — `coreograph_args = null`; add `tma_expected_cores = null`,
  `tma_core_diameter_mm = null` with one comment line: sweep unless `coreograph_args` is set.
- Modify: `subworkflows/local/utils_nfcore_histo_pipeline/main.nf` (`validateParams`, after the
  `use_tma_dearray requires use_preprocessing` assert)
- Modify: `nextflow_schema.json`, `assets/params_template*.yml` — generated, not edited
- Test: `tests/validate_params.nf.test`

**Interfaces:**

- Produces: `params.tma_expected_cores` (integer > 0), `params.tma_core_diameter_mm`
  (number > 0), `params.coreograph_args` (string or null). Sweep mode ⇔
  `params.use_tma_dearray && !params.coreograph_args`.

- [ ] **Step 1: Write failing tests** in `tests/validate_params.nf.test`, same style as the
      existing ones (`input[0] = [ ... ]`, `use_preprocessing: true`):
  - `"TMA sweep without expected cores or diameter is rejected"`: `use_tma_dearray: true`,
    neither `tma_*` → `function.failed`, stdout contains `tma_expected_cores` and
    `tma_core_diameter_mm` and `coreograph_args`.
  - `"TMA sweep with zero or negative values is rejected"`: `tma_expected_cores: 0,
tma_core_diameter_mm: 1.5` → failed, mentions `tma_expected_cores`.
  - `"TMA sweep with both values is accepted"`: `4` and `1.5` → `function.success`.
  - `"manual coreograph_args needs no tma params"`: `coreograph_args: '--downsampleFactor 4'`
    → `function.success`.
- [ ] **Step 2: Run, expect FAIL.** `nf-test test tests/validate_params.nf.test`
- [ ] **Step 3: Add the asserts.** Message (exact):
      `"use_tma_dearray needs tma_expected_cores (total cores on the slide) and tma_core_diameter_mm (core diameter in mm) to choose Coreograph's downsample factor. To set Coreograph's arguments yourself instead, set coreograph_args."`
      A second assert requires both values > 0, naming the offending param.
- [ ] **Step 4: Edit the schema by hand** (Task 0's hook lints it): in the
      `preprocessing_options` group, `tma_expected_cores` (`integer`, `minimum: 1`) and
      `tma_core_diameter_mm` (`number`, `exclusiveMinimum: 0`), each with a one-line
      description and help text saying they are required with `use_tma_dearray` unless
      `coreograph_args` is set; `coreograph_args` loses its default and its description
      says setting it skips the sweep. Let the prek hook regenerate the params templates.
- [ ] **Step 5: Run, expect PASS.** `nf-test test --tag validation`
- [ ] **Step 6: Commit** — `Add TMA core count and diameter params`

---

### Task 5: Wire the sweep into PREPROCESS_IMAGES

**Files:**

- Modify: `subworkflows/local/preprocess_images/main.nf:50-79` (the `use_tma_dearray` block)
- Modify: `conf/modules.config:49-58` (`COREOGRAPH`) and add `COREOGRAPH_DETECT`,
  `COREOGRAPH_SELECT` blocks
- Modify: `conf/sizes.config` — `COREOGRAPH_DETECT` at each size equal to `COREOGRAPH`'s line,
  `COREOGRAPH_SELECT` at `cpus = 1; memory = 2.GB * task.attempt; time = 30.m * task.attempt`,
  comment `// not exercised`
- Modify: `tests/preprocess_images.nf.test`, `tests/tma.nf.test`
- Modify: `containers.tsv` (regenerate)

**Interfaces:**

- Consumes: `COREOGRAPH_DETECT.out.results/.labels`, `COREOGRAPH_SELECT.out.selection/.report`,
  Task 4 params.
- Produces: in sweep mode, every core's meta has `downsample_factor: Integer`. Manual mode is
  today's graph, byte for byte.

Wiring (the part the spec's diagram does not pin):

```groovy
def SWEEP_FACTORS = [3, 4, 5, 6, 7]
ch_to_dearray = ASHLAR.out.tif
if (!params.coreograph_args) {
    COREOGRAPH_DETECT(ASHLAR.out.tif.combine(channel.fromList(SWEEP_FACTORS)))
    // size: releases each slide as soon as its own factors finish.
    COREOGRAPH_SELECT(COREOGRAPH_DETECT.out.results.groupTuple(size: SWEEP_FACTORS.size()))
    ch_to_dearray = ASHLAR.out.tif
        .join(COREOGRAPH_SELECT.out.selection)
        .map { meta, image, selection ->
            def choice = new groovy.json.JsonSlurper().parse(selection)
            if (choice.warning) { log.warn("${meta.id}: ${choice.warning}") }
            [meta + [downsample_factor: choice.downsample_factor as Integer], image]
        }
}
COREOGRAPH(ch_to_dearray)
```

`conf/modules.config`:

- `COREOGRAPH`: `ext.args = { params.coreograph_args ?: "--channel 0 --buffer 2 --sensitivity 0.3 --downsampleFactor ${meta.downsample_factor}" }`.
  One comment line: the closure is evaluated per task, so each slide gets its own k.
- `COREOGRAPH_DETECT`: `ext.args = { "--channel 0 --buffer 2 --sensitivity 0.3 --expected-cores ${params.tma_expected_cores} --core-diameter-mm ${params.tma_core_diameter_mm}" }`,
  `ext.prefix = { "${meta.id}" }`; `COREOGRAPH_SELECT`: `ext.prefix = { "${meta.id}" }`. Both
  publish to `${params.outdir}/preprocessing/dearray/sweep`, `versions.yml` dropped.

- [ ] **Step 1: Write failing tests.**
  - `tests/preprocess_images.nf.test`: both existing TMA tests set `tma_expected_cores = 4`,
    `tma_core_diameter_mm = 1.5`, and assert `metas.every { it.downsample_factor == 5 }` (the
    select stub's value). New test `"two slides each get their own sweep"` (Review Focus 5):
    cycles for `slideA` and `slideB`, assert five detect tasks per slide (10), two select
    tasks, and core ids from both slides with `slide` set correctly. New test
    `"coreograph_args skips the sweep"`: `coreograph_args = '--downsampleFactor 4 --channel 0 --buffer 2'`,
    assert no `COREOGRAPH_DETECT`/`COREOGRAPH_SELECT` in the trace and no
    `downsample_factor` in core metas.
  - `tests/tma.nf.test`: add the two `tma_*` params to both tests, and assert
    `names("COREOGRAPH_DETECT").size() == 5` and `names("COREOGRAPH_SELECT").size() == 1`.
- [ ] **Step 2: Run, expect FAIL.**
      `nf-test test tests/preprocess_images.nf.test tests/tma.nf.test`
- [ ] **Step 3: Implement the wiring, configs and sizes; regenerate the manifest** with
      `tools/container_manifest.py`.
- [ ] **Step 4: Run, expect PASS:** `nf-test test --tag stub,validation`,
      `tools/container_manifest.py --check`, `uv run pytest`,
      `uvx --from nf-core nf-core pipelines lint`.
- [ ] **Step 5: Commit** — `Wire Coreograph downsample sweep into preprocessing`

---

### Task 6: Exemplar-002, docs, metro map

**Files:**

- Modify: `conf/test_exemplar002.config:29-32` — drop `coreograph_args`; add
  `tma_expected_cores = 4` and `tma_core_diameter_mm = 1.5` with the comment
  `// Measured by hand; the sweep should pick k = 4.`
- Modify: `tests/exemplar002.nf.test`
- Modify: `docs/usage.md` (params table and the `coreograph_args` paragraph near line 77),
  `docs/output.md` (the `preprocessing/dearray/sweep/` files), `CHANGELOG.md` (breaking: TMA
  runs need `tma_*` or `coreograph_args`), `README.md:39` if wording needs it
- Modify: `docs/pipeline_paths.mmd`, regenerate `docs/images/pipeline_paths.svg`

- [ ] **Step 1: Add assertions** to `tests/exemplar002.nf.test`:
  - `names("COREOGRAPH_DETECT").size() == 5`, `names("COREOGRAPH_SELECT").size() == 1`.
  - `exemplar-002_selection.json` has `downsample_factor == 4` and no warning.
  - The copied code matches Coreograph:
    `path("$outputDir/preprocessing/dearray/sweep/exemplar-002_k4_centroids.txt").text == path("$outputDir/preprocessing/dearray/exemplar-002_centroids.txt").text`.
- [ ] **Step 2: Docs and CHANGELOG.** Usage: users give the core count and diameter; manual
      mode via `coreograph_args`; where to look (`*_sweep.tsv`, `*_sweep_overlays.png`).
- [ ] **Step 3: Metro map.** Add the sweep stations before `COREOGRAPH` in
      `docs/pipeline_paths.mmd`, run
      `nf-metro render docs/pipeline_paths.mmd -o docs/images/pipeline_paths.svg --animate`,
      and add `--animate` to the render command in `CLAUDE.md` §3 and `CONTRIBUTING`.
      **Human step:** the user looks at the SVG.
- [ ] **Step 4: Verify locally:** `prek run --all-files`, `nf-test test --tag stub,validation`,
      `uv run pytest`.
- [ ] **Step 5: Commit** — `Run exemplar-002 through the Coreograph sweep`
- [ ] **Step 6: Hand over the cluster command** (the user submits):
      `nf-test test tests/exemplar002.nf.test --profile test_exemplar002,singularity,size_small,slurm`.
      What it confirms: k = 4 is chosen, the k = 4 centroids equal Coreograph's (and with
      them the strided read and the copied block), the detect process runs in the real
      image. After the run, refit `COREOGRAPH_DETECT` sizes from the trace.
