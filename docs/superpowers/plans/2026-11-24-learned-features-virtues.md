# Learned features (VirTues) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With `use_virtues`, every store gains `{method}_virtues` (per cell), `virtues_niches`
with `virtues_niches_table` (per 128 µm tissue square) and `virtues_tissue` (per store): 512-number
VirTues embeddings.

**Architecture:**

- After segmentation, a CPU `VIRTUES_HISTOGRAM` per store feeds a `VIRTUES_STATS` per slide, which
  writes the slide's clip, mean and SD per marker (`virtues_stats.json`).
- One GPU `VIRTUES` task per store runs our tiled runner (`bin/virtues_cells.py`). It calls
  upstream's encoder unchanged; the averaging into cells, squares and tissue is ours.
- `WRITE_FEATURES` stays the only writer, now also for shapes and for tables that are not per
  method.

**Tech Stack:** Nextflow DSL2, nf-test, Python 3.11 or 3.12, numpy, shapely, spatialdata, anndata,
PyTorch with FlashAttention 2, `virtues` at `d2c25e1`, ESM-2 (`fair-esm`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-learned-features-virtues-design.md`. Its "Settled with
you" list is the user's decisions; do not reopen them.

## Global Constraints

- **No network at run time.** Weights, ESM-2 and UniProt sequences are baked into the image, which
  sets `HF_HUB_OFFLINE=1`.
- **Images.** `docker.io/josenimo/virtues:d2c25e1` for `VIRTUES`; `docker.io/josenimo/sopa:2.3.0`
  for `VIRTUES_HISTOGRAM`, `VIRTUES_STATS` and `WRITE_FEATURES`. The user pushes images. Agents
  never `docker push`, `git push`, `sbatch` or `srun`; they write the command for the user.
- **`bin/virtues_stats.py` imports no torch**, so it runs in the sopa image.
- **Schema.** Optional steps are booleans with `default: false`. Edit `nextflow_schema.json` by
  hand. Never edit `assets/params_template*.yml`.
- **Stubs.** Every module that creates a file has a `stub:` block, updated in the same commit as
  its outputs.
- **Manifest.** Regenerate `containers.tsv` with `tools/container_manifest.py` after adding a
  module.
- **Errors in operators.** `error()`, never `assert`.
- **Commits.** `git add` with explicit paths. Titles under ~60 characters, a body of a few lines or
  none, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. If prek reformats, re-add
  and commit again.
- **Comments.** One line of "why".
- **Pinned values.**
  - Model scale: 1.0 µm/px. Model grid `floor(n_image × pixel_size)` per axis; model pixel `k`
    covers image interval `[k / pixel_size, (k + 1) / pixel_size)`.
  - Crops 128 px, patches 8 px (16 × 16 per crop), crop step 42, padding 120 px, tile 2048 model
    px, embedding size 512, GPU batch 32 crops (upstream's `chunk_size`).
  - Statistics: quantile 0.99 (numpy default `linear` method), 65 536 histogram bins (uint16),
    population SD, statistics file `format: 1`.
  - Blur: 3 × 3 Gaussian, sigma 1.0, applied after standardisation.
  - Niches: kept when tissue fraction ≥ 0.30.
  - Output `X`: float16. Accumulation: float32 sums, float64 weights.
- **Licence.** Only the `sp32` weights. Never copy spora-bench code (CC BY-NC-ND). Upstream
  `virtues` and spora-io are MIT; their functions are called, not copied, except the one test
  reference in Task 4, which cites the commit.
- **Order.** Task 1 is a gate for Tasks 5 and 11. Tasks 2, 3, 4 and 6 do not need the image and
  may proceed while the user runs Task 1's cluster check.

## Review Focus

1. **A cell or square near a tile edge or the image edge.** It gets exactly the crops upstream
   would give it, so its row is identical for any tile size. Pinned in Task 4.
2. **A store with no tissue square kept** (a tiny or nearly empty TMA core). No niche files are
   written, the tissue row is NaN with `n_niches = 0`, and the run goes on. Pinned in Tasks 4 and 6.
3. **A marker that is constant or absent over a slide's tissue** (SD 0, or no tissue pixels). The
   statistics task fails naming the slide and marker, instead of writing NaN or infinity that the
   GPU task would turn into garbage. Pinned in Task 3.
4. **Backsub in front of VirTues.** If backsub drops the `uniprot_id` column or writes a float
   image, the run stops with a message saying so, instead of embedding nothing or histogramming
   floats. Facts from Task 1; pinned in Tasks 3 and 8.
5. **GPU only where needed.** `VIRTUES` gets a GPU; `VIRTUES_HISTOGRAM` and `VIRTUES_STATS` do
   not, so the statistics never queue for GPUs. Pinned in Task 7.

---

### Task 1: VirTues image spike and upstream facts

**Gate.** If the image cannot import `flash_attn` and run the forward pass on a cluster GPU, stop
and report before Task 5. If backsub writes a float image or drops extra marker-sheet columns,
record it and report before Task 8; the user decides.

**Files:**

- Create: `tools/containers/virtues/Dockerfile`.
- Create: `tools/containers/virtues/README.md`: build, save-to-tar, cluster check, in a few lines.
- Create: `tools/containers/virtues/check_image.py`, run inside the image.

**Interfaces:**

- Produces: the local image `docker.io/josenimo/virtues:d2c25e1`, with these environment
  variables, read by Task 5:
  - `VIRTUES_WEIGHTS=/opt/virtues/sp32/model.safetensors`
  - `VIRTUES_UNIPROT=/opt/uniprot/human_sprot_isoforms.fasta`
  - `VIRTUES_UNIPROT_RELEASE`: the `X-UniProt-Release` header of the download
  - `VIRTUES_COMMIT=d2c25e1`
  - `VIRTUES_SRC=/opt/virtues-src`, the repository checkout, including `assets/example_dataset`
    (40 MB), for parity
  - `TORCH_HOME=/opt/torch`, holding the ESM-2 `esm2_t30_150M_UR50D` weights
  - `HF_HUB_OFFLINE=1`
- Produces: findings in the SDD ledger and the README:
  - torch, CUDA, FlashAttention, spatialdata versions in the image;
  - the shape and dtype of `encoder_output.patch_summary_tokens` per crop;
  - our ESM-2 embedding of each ID in `assets/example_dataset/marker_embeddings/` against the
    bundled `.pt`: max abs difference;
  - backsub: its output image dtype, and whether its `--marker-output` CSV keeps a column it does
    not know (read its source in its container, `modules/nf-core/backsub`).

- [ ] **Step 1: Write the Dockerfile.**
  - Base: `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`. Add the FlashAttention 2 wheel matching
    its torch, CUDA, Python and C++ ABI from the Dao-AILab GitHub releases (start from
    `flash_attn-2.7.4.post1+cu12torch2.5cxx11abiFALSE`). If no wheel matches, pick another base and
    wheel pair; never compile FlashAttention.
  - `pip install --no-deps` `virtues` from `git+https://github.com/bunnelab/virtues@d2c25e1` and
    spora-io at `ef15868`, then their runtime imports at exact versions (`fair-esm`, `omegaconf`,
    `safetensors`, `einops` and whatever the import check shows missing).
  - spatialdata, anndata and geopandas at the versions in `docker.io/josenimo/sopa:2.3.0`
    (`docker run --rm docker.io/josenimo/sopa:2.3.0 pip list`), so both images read the same store.
  - Bake `virtues-sp32/model.safetensors` from HF `bunnelab/virtues`, ESM-2 150M via
    `esm.pretrained.esm2_t30_150M_UR50D()`, and
    `https://rest.uniprot.org/uniprotkb/stream?format=fasta&includeIsoform=true&query=(organism_id:9606)+AND+(reviewed:true)`.
- [ ] **Step 2: Build it.**
      Run: `docker buildx build --platform linux/amd64 -t docker.io/josenimo/virtues:d2c25e1 tools/containers/virtues`
      Expected: success.
- [ ] **Step 3: Check offline on the Mac.** `check_image.py --cpu-only` with `--network none`:
      imports `virtues`, spatialdata and `esm`; loads the safetensors into
      `MultiplexVirtues(prior_bias_embeddings=...)` with `strict=True`; compares ESM-2 embeddings
      with the bundled `.pt`. `flash_attn` is not imported on the Mac.
      Expected: no exception; ESM difference printed.
- [ ] **Step 4: Write the cluster check for the user.** `check_image.py` without `--cpu-only` also
      imports `flash_attn`, runs `compute_cell_tokens` on the bundled example core as notebook 2
      does, and prints the token shape. Write the `apptainer exec --nv` command and the image
      staging commands in the README. The user pushes, stages and submits.
      Expected (from the user): it runs and prints the shapes.
- [ ] **Step 5: Record the backsub facts** from its source.
- [ ] **Step 6: Commit** the three files: `VirTues image spike`.

### Task 2: Parameters, `uniprot_id`, validation and `featureSpecs`

**Files:**

- Modify: `nextflow_schema.json` (learned features group), `nextflow.config`,
  `assets/schema_marker.json`, `modules/local/utils.nf`,
  `subworkflows/local/utils_nfcore_histo_pipeline/main.nf`.
- Create: `tests/stub_data/markers_virtues.csv`: `tests/stub_data/markers.csv` plus a
  `uniprot_id` column, `P08246` for ELANE and `P11215` for CD11B, empty for the DNA rows.
- Test: `tests/feature_specs.nf.test`, `tests/validate_params.nf.test`,
  `tests/validate_virtues_markers.nf.test` (new).

**Interfaces:**

- Produces: `use_virtues` (boolean, `false`; help text lists the requirements) and
  `virtues_stats` (string, `format: file-path`, `exists: true`, `pattern: "^\\S+\\.json$"`,
  `hidden: true`, default `null`).
- Produces: marker sheet column `uniprot_id`: string, default `null`, `meta: uniprot_id`, pattern
  `^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})(-[0-9]+)?$`, error
  message "uniprot_id must be a UniProt accession, optionally with an isoform suffix (e.g. P08575 or
  P08575-8)".
- Produces: `featureSpecs` appends, with `use_virtues`,
  `[name: 'virtues', model: 'virtues', channels: null, pixel_size: pixelSize(args), stats: args.virtues_stats ?: null, gpu: args.use_gpu ? true : false]`.
- Produces in `utils.nf`: `virtuesChannels(List rows) -> List<List<String>>`, `[marker_name,
uniprot_id]` of each row with a non-empty `uniprot_id`, in sheet order; and
  `virtuesUnembedded(List rows) -> List<String>`, the other rows' `marker_name`.
- Produces: `validateVirtuesMarkers(rows, where, stats = null)` in the utils subworkflow, called
  from the marker-sheet loop when `params.use_virtues`, with `stats` parsed by `JsonSlurper` from
  `params.virtues_stats` when set. It checks the rows backsub keeps
  (`params.use_backsub ? rows.findAll { !it.remove } : rows`).
- Messages (asserted verbatim in tests):
  - `use_virtues requires use_gpu: VirTues runs on FlashAttention, which has no CPU path.`
  - `use_virtues requires use_preprocessing: UniProt IDs come from the marker sheet, which pre-stitched input does not have.`
  - `use_virtues requires use_tissue_segmentation: intensity statistics are computed over tissue pixels.`
  - `use_virtues requires segment_cells: VirTues embeds cells, so there must be a cell segmentation.`
  - `use_virtues requires pixel_size (microns per pixel of the image): VirTues runs at 1 µm per pixel.`
  - `virtues_stats is set but use_virtues is not.`
  - `${where}: use_virtues needs a uniprot_id on at least one marker row; a channel is embedded only when it has one.`
  - `${where}: DNA stains are not embedded; remove the uniprot_id from: ${names}.`
  - `${where}: uniprot_id must be unique. Repeated: ${ids}.`
  - `${where}: virtues_stats has no statistics for: ${names}.`
  - `${where}: virtues_stats records a different uniprot_id for: ${name} (sheet ${a}, stats ${b}).`

- [ ] **Step 1: Write the failing tests.**
  - `featureSpecs`: `[use_virtues: true, pixel_size: 0.65]` gives one spec with `model ==
'virtues'`, `channels == null`, `stats == null`; with `virtues_stats: '/x/s.json'`, `stats ==
'/x/s.json'`; with both `use_nimbus` and `use_virtues`, two specs, Nimbus first.
  - `virtuesChannels` and `virtuesUnembedded` on four rows (dna without ID, two markers with IDs,
    one marker without) give the two pairs in order and the other two names.
  - `validateParams`: each of the six parameter messages, each from a params map that is valid
    except for that one rule.
  - `validateVirtuesMarkers`: each of the five sheet messages; a valid sheet passes; with
    `use_backsub` a `remove: true` row's ID is ignored by every rule.
  - The schema rejects `uniprot_id = CD3` and accepts `P08575-8` (follow
    `tests/validate_marker_sheet_column.nf.test`'s way of running the schema).
- [ ] **Step 2: Run them and confirm they fail.**
      Run: `nf-test test tests/feature_specs.nf.test tests/validate_params.nf.test tests/validate_virtues_markers.nf.test`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.**
      Run: `nf-test test --tag validation && nf-test test tests/feature_specs.nf.test`
      Expected: all pass; the schema hook passes.
- [ ] **Step 5: Commit.** `Add use_virtues, virtues_stats and uniprot_id`

### Task 3: Model scale and slide statistics

**Files:**

- Create: `bin/virtues_stats.py`.
- Test: `tests/unit/test_virtues_stats.py`.

**Interfaces:**

- Produces constants: `MODEL_UM_PER_PX = 1.0`, `QUANTILE = 0.99`, `N_BINS = 65536`,
  `STATS_FORMAT = 1`.
- Produces: `model_shape(image_yx: tuple[int, int], pixel_size: float) -> tuple[int, int]`.
- Produces: `resample_window(image, channel: int, y0: int, y1: int, x0: int, x1: int, pixel_size: float) -> np.ndarray`,
  float32 `(y1 - y0, x1 - x0)` in model coordinates. `image` is `(c, y, x)` dask or numpy; it reads
  only the image rows and columns it needs. Area-weighted and separable. Each output is a fixed-order
  sum over its at most `ceil(1 / pixel_size) + 1` contributing input pixels per axis (rows, then
  columns), in float64, vectorised over outputs. No matrix product: its summation order depends on
  the window's shape, which would break bit-for-bit window independence. `pixel_size == 1.0`
  returns the image values as float32.
- Produces: `tissue_mask(polygons, y0, y1, x0, x1, pixel_size) -> np.ndarray[bool]`, model pixel
  `(r, c)` is tissue when its centre `((c + 0.5) / pixel_size, (r + 0.5) / pixel_size)` in image
  coordinates is inside a polygon (`shapely.contains_xy`).
- Produces: `histogram(image, polygons, channels: list[int], pixel_size, rows: int = 2048) -> np.ndarray`,
  int64 `(len(channels), N_BINS)`, over tissue pixels, values `np.rint` and clipped to
  `[0, N_BINS - 1]`, in blocks of `rows` model rows. Raises `TypeError` naming the dtype unless
  `image.dtype` is an unsigned integer.
- Produces: `stats_from_histogram(counts: np.ndarray) -> dict`, keys `cap`, `mean`, `sd`,
  `tissue_pixels`. `cap` equals `np.quantile(pixels, 0.99)`; `mean` and `sd` are of
  `log1p(min(v, cap))`, population SD, two-pass. Raises `ValueError` when there are no pixels or
  `sd == 0`; the CLI turns it into a message naming slide and marker.
- Produces: `load_stats(path, channels: list[tuple[str, str]]) -> dict[str, dict]`, which checks
  `format == STATS_FORMAT` and that each `(name, id)` is present with that ID, raising `ValueError`
  naming what differs.
- Produces the CLI:

  ```text
  virtues_stats.py histogram --sdata S --channels NAME:ID,... --pixel-size F --output SAMPLE_virtues_hist.npz
  virtues_stats.py combine --slide SL --pixel-size F --output SL_virtues_stats.json H1.npz [H2.npz ...]
  ```

  - `histogram` reads the store's segmentation image (`resolve_segmentation.store_image_key`,
    scale0 as `nimbus_cells.py` does) and `region_of_interest`. The npz holds `counts`, `markers`,
    `uniprot_ids`, `sample`. Exits 1 naming the dtype for a non-integer image, and naming the
    missing element when there is no `region_of_interest`.
  - `combine` refuses inputs whose markers or IDs differ, sums counts, and writes
    `{"format": 1, "slide": SL, "cores": [...], "model_um_per_px": 1.0, "pixel_size": F,
"markers": {name: {"uniprot_id", "cap", "mean", "sd", "tissue_pixels"}}}`.

- [ ] **Step 1: Write the failing tests.**
  - `test_resample_identity_at_one_um`.
  - `test_resample_area_average`: pixel size 0.5, a 4 × 4 ramp gives the hand-computed 2 × 2 means.
  - `test_resample_window_independent_bit_for_bit`: pixel size 0.65, random uint16 300 × 300; 20
    random windows equal (`np.array_equal`) the same region of the whole-image result.
  - `test_resample_upsampling`: pixel size 2.0 gives a grid twice the size, each value its source
    pixel.
  - `test_tissue_mask_pixel_centres`: a square polygon covering image `[0, 10)` at pixel size 0.5
    marks model pixels 0 to 4.
  - `test_stats_equal_numpy`: random tissue pixels from two "cores"; summed histograms give `cap`
    equal to `np.quantile(pooled, 0.99)`, and `mean`, `sd` equal to `np.mean`, `np.std` of
    `np.log1p(np.minimum(pooled, cap))`, rtol 1e-12.
  - `test_histogram_only_tissue`: pixels outside the polygon change nothing.
  - `test_float_image_refused`, `test_constant_marker_refused`, `test_no_tissue_refused`.
  - `test_combine_refuses_mismatched_markers`, `test_load_stats_id_mismatch`.
- [ ] **Step 2: Run and confirm failure.** `pytest tests/unit/test_virtues_stats.py -v`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** `pytest tests/unit/test_virtues_stats.py -v && ruff check bin/virtues_stats.py`
      Expected: pass.
- [ ] **Step 5: Commit.** `VirTues: model scale and slide statistics`

### Task 4: Tiled runner core, with a fake encoder

**Files:**

- Create: `bin/virtues_cells.py` (pure functions here; model and CLI in Task 5).
- Test: `tests/unit/test_virtues_cells.py`.

**Interfaces:**

- Consumes: `resample_window`, `tissue_mask`, `model_shape` from Task 3.
- Produces constants: `CROP = 128`, `PATCH = 8`, `STEP = 42`, `PAD = 120`, `TILE = 2048`,
  `BATCH = 32`, `NICHE_MIN_TISSUE = 0.30`, `BLUR_SIGMA = 1.0`.
- Coordinates: "padded" model coordinates, the model grid shifted by `PAD` on each side, as upstream
  pads before cutting crops.
- Produces: `uniform_crops(h: int, w: int) -> list[tuple[int, int]]`, the sorted crop origins of
  upstream `_get_uniform_crops(img, STEP, CROP)` for a padded image of `h × w`, without the image.
- Produces: `model_input(read_raw, stats, y0, y1, x0, x1, padded_shape) -> np.ndarray`, float32
  `(c, y1 - y0, x1 - x0)` in padded coordinates:
  1. raw values for one pixel more on each side, from `read_raw(c, y0, y1, x0, x1)` in model
     coordinates; 0 outside the image (upstream's zero pad; beyond the pad too, which equals
     torchvision's reflect border because the pad is wider than the blur radius);
  2. `(log1p(min(x, cap)) - mean) / sd` per channel;
  3. the 3 × 3 Gaussian (torchvision's kernel: `exp(-0.5 * (k / 1.0)**2)` for `k` in -1, 0, 1,
     normalised), separable, keeping the interior.
- `read_input(y0, y1, x0, x1)` below is `model_input` bound to a store's `read_raw`, statistics
  (arrays `cap`, `mean`, `sd` in channel order) and `padded_shape`; `read_tissue(y0, y1, x0, x1)`
  is `tissue_mask` bound to `region_of_interest`, in model coordinates.
- Produces: `encode` protocol: `encode(crops: np.ndarray) -> np.ndarray`, `(n, c, 128, 128)`
  float32 in, `(n, 16, 16, D)` float32 out. The test encoder returns each patch's mean per channel
  (`D = c`).
- Produces: `CellSource(read_labels, centroids, bboxes)`, a dataclass. `read_labels(y0, y1, x0,
x1)` returns int32 labels `1..n` in padded coordinates, 0 for background; `centroids` and
  `bboxes` are `(n, 2)` and `(n, 4)` (`y0, y1, x0, x1`) in padded coordinates.
- Produces: `label_reader(geoms, pixel_size) -> Callable`, for the CLI: pixel-centre rule as
  `tissue_mask`, geoms in image coordinates; where cells overlap, the earlier geom wins, so a
  pixel's label does not depend on the window.
- Produces: `cell_embeddings(read_input, sources: dict[str, CellSource], padded_shape, encode, tile=TILE, batch=BATCH) -> dict[str, tuple[np.ndarray, np.ndarray]]`,
  per method `(emb float32 (n, D), weight float64 (n,))`, NaN rows where the weight is 0.
  - A cell belongs to the tile (`tile × tile`, padded coordinates) holding its centroid, for each
    method separately.
  - Per tile, the crops are those of `uniform_crops` whose box meets an owned cell's bbox, for any
    method; they are encoded once, in batches of `batch`, in upstream's sorted order.
  - Per crop and method, the cell × patch pixel counts (`np.bincount` on `patch * (n + 1) +
label`) weight the patch tokens into float32 sums for that tile's owned cells only. Iterating
    crops in global sorted order makes each cell's sums add in the same order for any tile size.
- Produces: `niche_embeddings(read_input, read_tissue, image_shape_model, encode, batch=BATCH) -> tuple[list[tuple[int, int]], np.ndarray, np.ndarray]`,
  the kept squares' origins in model coordinates, their tissue fractions, and float32
  `(k, D)` embeddings, the mean of each square's 256 patch tokens. Squares are on a 128 px grid
  from the model origin, only those fully inside the image, read through `model_input` at
  `origin + PAD`. Kept when tissue fraction ≥ `NICHE_MIN_TISSUE`. Read one tile row at a time.
- Produces: `tissue_embedding(niches: np.ndarray) -> np.ndarray`, the mean of the rows; NaN `(D,)`
  when there are none.

- [ ] **Step 1: Write the failing tests.** Synthetic images and shapely boxes; the patch-mean
      encoder; statistics with `cap` large, `mean = 0`, `sd = 1`.
  - `test_crop_grid_equals_upstream`: a copy of upstream `_get_uniform_crops` from `d2c25e1` in
    the test file (MIT, with a comment citing the commit), for shapes 128 × 128, 300 × 517 and
    1000 × 1000.
  - `test_tiled_equals_whole_image_exactly`: 40 cells, many on tile edges, `tile` 64, 200 and
    4096; `np.array_equal`.
  - `test_cell_matches_upstream_averaging`: a direct port of upstream's per-crop loop on the whole
    padded image (in the test) gives the same rows, rtol 1e-6.
  - `test_two_methods_equal_one_at_a_time`.
  - `test_cell_without_pixel_is_nan`: a sliver between pixel centres.
  - `test_overlap_earlier_cell_wins`.
  - `test_model_input_window_independent`: windows at the image edge and inside equal the
    whole-image result, including the zero pad and the blur.
  - `test_niche_grid_and_threshold`: a 300 × 300 image gives 4 squares; a polygon covering 29% of
    one square drops it, 31% keeps it.
  - `test_niche_is_patch_mean`, `test_tissue_is_mean_of_kept_niches`,
    `test_no_niche_gives_nan_tissue`.
- [ ] **Step 2: Run and confirm failure.** `pytest tests/unit/test_virtues_cells.py -v`
- [ ] **Step 3: Implement.** Never hold more than one window's input and labels at once.
- [ ] **Step 4: Run.** `pytest tests/unit/test_virtues_cells.py -v && ruff check bin/virtues_cells.py`
- [ ] **Step 5: Commit.** `VirTues runner: crops, tiles, cells, niches`

### Task 5: Model, CLI, outputs and the parity tool

**Files:**

- Modify: `bin/virtues_cells.py`.
- Create: `tools/virtues_parity.py`, run in the image on a cluster GPU.
- Test: `tests/unit/test_virtues_cells.py` (CLI with the fake encoder); `tests/unit/test_virtues_model.py`,
  skipped unless `virtues` and `flash_attn` import and CUDA is available.

**Interfaces:**

- Consumes: Tasks 1, 3, 4.
- Produces: `uniprot_sequences(fasta: Path, ids: list[str]) -> dict[str, str]`, from headers
  `>sp|ACC|...`; raises `KeyError` naming the absent IDs.
- Produces: `load_virtues(weights: Path, sequences: list[str], device: str)`: ESM-2 embeddings
  with upstream `ESMWrapper("esm2_t30_150M_UR50D", device).embed_sequence`, stacked in channel
  order as `prior_bias_embeddings`; `MultiplexVirtues(prior_bias_embeddings=...)`;
  `load_state_dict(safetensors.torch.load_file(weights))`; `.to(device).eval()`.
- Produces: `virtues_encoder(model, n_channels: int, device: str) -> encode`: calls
  `model.encoder.forward_list(crops, [arange(n_channels)] * n, multiplex_mask=None)` under
  `torch.no_grad()` and `torch.amp.autocast('cuda')`, returning `patch_summary_tokens` as float32
  numpy `(n, 16, 16, 512)`.
- Produces: `main(argv=None, encode=None) -> int`; tests inject `encode`, otherwise the model is
  loaded.
- Produces the CLI:

  ```text
  virtues_cells.py --sdata S --methods M1,M2 --channels NAME:ID,... --unembedded N1,N2
                   --stats SL_virtues_stats.json --pixel-size F --device cuda
                   [--batch-size 32] [--outdir .]
  ```

  - Reads the segmentation image, `region_of_interest`, and per method `{M}_cells` and
    `{M}_table`'s obs, as `nimbus_cells.py` does. Rows follow `{M}_table.obs_names`.
  - Exits 1 naming them: an unknown channel, an ID not in the UniProt file, statistics that do not
    match the channels (`load_stats`), a non-CUDA device.
  - Writes `{M}_virtues.h5ad` per method; `virtues_niches.parquet` and `virtues_niches_table.h5ad`
    only when a square is kept; `virtues_tissue.h5ad`; `virtues.json`.
  - `{M}_virtues`: `TableModel.parse(..., region="{M}_cells", region_key="region",
instance_key="cell_id")`, `X` float16, `var_names` `virtues_0` … `virtues_511`, `obs` copied
    (`region`, `slide`, `core_id`, `cell_id` where present).
  - `virtues_niches`: square polygons in image coordinates (model origin ÷ `pixel_size`), index
    `niche_0` … in grid order. `virtues_niches_table`: region `virtues_niches`, instance key
    `niche_id`, `obs` `niche_id`, `tissue_fraction`, and `slide`, `core_id` from `{M}_table` where
    present.
  - `virtues_tissue`: 1 row, `obs` `slide`, `core_id`, `n_niches`; parsed without a region.
  - `uns['virtues']` on every table and in `virtues.json`: `virtues_commit`, `weights`,
    `weights_sha256`, `esm_model`, `uniprot_release`, `channels` (name → ID), `unembedded`,
    `stats`, `pixel_size`, `model_um_per_px`, `crop_size`, `crop_step`, `patch_size`, `padding`,
    `tile_size`, `batch_size`, `device`, `n_cells` and `n_cells_without_pixel` (per method),
    `n_niches_kept`, `n_niches_dropped`.

- Produces: `tools/virtues_parity.py OUT.json`: on the bundled example core, runs upstream exactly
  as notebook 2 (spora-io standardiser with the blur, 120 px pad, `compute_cell_tokens`) at
  `chunk_size` 32 and 8, and our `cell_embeddings` on the same raw image, mask and statistics
  (written in the `virtues_stats.json` format). Reports per-cell cosine (min, median), max abs
  difference, for upstream vs itself and ours vs upstream.

- [ ] **Step 1: Write the failing tests.**
  - `test_cli_outputs_layout`: a tiny store (as in `tests/unit/test_aggregate_compartments.py`)
    with `region_of_interest`, two methods, `main(argv, encode=fake)`: row names, float16,
    `var_names`, `uns` keys, niche polygon coordinates, the tissue table's single row.
  - `test_cli_no_niche_writes_no_niche_files`.
  - `test_unknown_uniprot_id_exits_naming_it`, `test_stats_mismatch_exits`.
  - Model tests: `test_encoder_shape`, `test_determinism` (the same crops twice, equal).
- [ ] **Step 2: Run and confirm failure.** `pytest tests/unit/test_virtues_cells.py -v`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** `pytest tests/unit -q` (model tests skipped). The model tests and the parity
      tool run on the cluster in Task 11.
- [ ] **Step 5: Commit.** `VirTues runner: model, CLI and parity tool`

### Task 6: Writer, segmentation writer and merge

**Files:**

- Modify: `bin/write_features.py`, `bin/write_segmentations.py`, `bin/merge_spatialdata.py`.
- Test: `tests/unit/test_write_features.py`, `tests/unit/test_merge_spatialdata.py`, the existing
  `write_segmentations` tests.

**Interfaces:**

- Produces: `write_features(sdata_path: Path, tables: list[Path], shapes: list[Path] = ()) -> None`.
  Each table's rows are checked by its region, before anything is touched:
  - region `{M}_cells`: `obs_names` equal `tables/{M}_table`'s (Nimbus and VirTues cells);
  - region a shapes file in this write: the instance key column equals that file's index, in
    order;
  - no region (`virtues_tissue`): no check;
  - any other region: `ValueError` naming the table.
    Then shapes and tables of the same names are removed by path, the store reconsolidated, shapes
    written with the segmentation image's transformations (as `write_segmentations` does), then
    tables. CLI: `--tables` and `--shapes`.
- Produces: `RESERVED` in `write_segmentations.py` becomes
  `^((cellpose|instanseg)_(cells|nuclei|cytoplasm|table|nimbus|virtues)|virtues_(niches|niches_table|tissue))$`,
  with `LEARNED_MODELS = ("nimbus", "virtues")`.
- Produces: `retarget_table` returns a table without `spatialdata_attrs` or with `region` `None`
  unchanged; it is still renamed `{core}__{name}` by `merge`.

- [ ] **Step 1: Write the failing tests.**
  - `test_writes_niches_shapes_and_table`, `test_writes_unannotated_tissue_table`,
    `test_niche_table_rows_must_match_shapes`, `test_nimbus_tables_still_checked_against_method_table`,
    `test_rerun_is_idempotent` (with shapes).
  - `test_write_segmentations_removes_stale_virtues_elements`: all four names.
  - Replace `test_missing_attrs_refused` with `test_unannotated_table_copied_unchanged`; add
    `test_tissue_table_renamed_per_core`.
- [ ] **Step 2: Run and confirm failure.** `pytest tests/unit/test_write_features.py tests/unit/test_merge_spatialdata.py -v`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** `pytest tests/unit -q`
- [ ] **Step 5: Commit.** `Writer and merge: shapes and unannotated tables`

### Task 7: Modules and configuration

**Files:**

- Create: `modules/local/virtues/`, `modules/local/virtues_histogram/`,
  `modules/local/virtues_stats/`, each `main.nf`, `meta.yml`, `environment.yml`.
- Modify: `modules/local/write_features/main.nf` and `meta.yml`, `conf/base.config`,
  `conf/gpu.config`, `conf/modules.config`, `containers.tsv`.

**Interfaces:**

- Produces: `VIRTUES_HISTOGRAM`: input `tuple val(meta), path(sdata_path), val(spec)`; output
  `tuple val(meta), path("${meta.sample}_virtues_hist.npz")`, `versions.yml`; label `process_low`;
  sopa image; tag `"${meta.sample}:virtues_histogram"`.
- Produces: `VIRTUES_STATS`: input `tuple val(slide), path(hists), val(spec)`; output
  `tuple val(slide), path("${slide}_virtues_stats.json")`, `versions.yml`; label
  `process_single`; sopa image.
- Produces: `VIRTUES`: input `tuple val(meta), path(sdata_path), val(methods), val(spec), path(stats)`;
  output `tuple val(meta), path("*.{h5ad,parquet}")`, `tuple val(meta), path("virtues.json")`,
  `versions.yml`; labels `process_medium`, `process_long`; the `VirTues` image; tag
  `"${meta.sample}:virtues"`. The script runs `NIMBUS`' `gpu_check` and fails without
  `task.accelerator` ("use_virtues: VIRTUES needs a GPU"). `versions.yml` records `virtues`
  (`$VIRTUES_COMMIT`), `torch`, `flash_attn`. The stub touches each `${m}_virtues.h5ad`,
  `virtues_niches.parquet`, `virtues_niches_table.h5ad`, `virtues_tissue.h5ad`, `virtues.json`.
- Each of the three stubs also writes `${task.accelerator ? 'gpu' : 'none'}` to `.accelerator` in
  its work directory (not an output), for the stub tests.
- Produces: `WRITE_FEATURES` input `tuple val(meta), path(sdata_path), path(features)`; its script
  passes `*.h5ad` as `--tables` and `*.parquet` as `--shapes`.
- Config:
  - `conf/gpu.config` selector `'SEGMENT_PATCH_(CELLPOSE|INSTANSEG)|NIMBUS|VIRTUES'`.
  - `conf/base.config`: `withName: 'VIRTUES' { cpus = 4 }`.
  - `conf/modules.config`: publish `VIRTUES_STATS` JSON to `learned_features/`, and `VIRTUES`'
    `virtues.json` as `${meta.sample}_virtues.json`.

- [ ] **Step 1: Write the modules and config.**
- [ ] **Step 2: Regenerate and check the manifest.**
      Run: `tools/container_manifest.py && tools/container_manifest.py --check && prek run --all-files`
      Expected: a `josenimo/virtues:d2c25e1` row; clean.
- [ ] **Step 3: Commit.** `Add VIRTUES, VIRTUES_HISTOGRAM and VIRTUES_STATS`

### Task 8: `LEARNED_FEATURES` wiring

**Files:**

- Modify: `subworkflows/local/learned_features/main.nf` and `meta.yml`, `docs/pipeline_paths.mmd`.
- Test: `tests/virtues.nf.test` (new); `tests/nimbus.nf.test` must still pass.

**Interfaces:**

- Consumes: Tasks 2 and 7.
- Changes in `LEARNED_FEATURES`:
  - The unknown-model `error()` accepts `virtues`. Nimbus rows stay per method; VirTues gets one
    row per store, with `methods` and the spec resolved as
    `spec + [channels: virtuesChannels(rows), unembedded: virtuesUnembedded(rows)]`.
  - An empty `virtuesChannels(rows)` fails with
    `error("Sample '${meta.sample}': no marker row with a uniprot_id reached VirTues. With use_backsub, check that backsub kept the uniprot_id column.")`.
  - Slide key: `meta.slide ?: meta.sample`. Histograms are grouped per slide with `groupTuple()`
    (core counts are not known in advance, so it waits for every store). With `spec.stats`, the
    statistics tasks are skipped and `file(spec.stats)` goes to every store.
  - Statistics join back to stores with `combine(..., by: 0)` on the slide key, since a slide has
    many stores.
  - Per store, every model's outputs are grouped with
    `groupKey(sdata_dir, n_outputs)`, where
    `n_outputs = specs.sum { s -> s.model == 'virtues' ? 1 : methods.size() }`, each item a list of
    files, flattened and sorted by name for `WRITE_FEATURES`.
  - `VIRTUES_STATS` and `VIRTUES` versions are mixed in.

- [ ] **Step 1: Write the failing tests** in `tests/virtues.nf.test` (profile `test,laptop`,
      `-stub`, tags `stub`, `pipeline`), building the sample sheet as `tests/tma.nf.test` does with
      `tests/stub_data/markers_virtues.csv`, and `use_virtues`, `use_gpu`, `use_tissue_segmentation`,
      `pixel_size = 0.65`.
  - `test("one method: histogram, stats, one VIRTUES, one write")`: one of each; QC starts after
    `WRITE_FEATURES` ends; `learned_features/testslide_virtues_stats.json` and
    `learned_features/testslide_virtues.json` published; `VIRTUES` in the versions file; `.accelerator`
    is `gpu` for `VIRTUES` and `none` for the other two.
  - `test("two methods: one VIRTUES for both")`, adding InstanSeg.
  - `test("TMA: one stats task per slide, one VIRTUES per core")`, with `tests/tma.nf.test`'s
    params: 4 histograms, 1 stats, 4 `VIRTUES`.
  - `test("virtues_stats given: no statistics tasks")`, with a stats file written in setup.
  - `test("with Nimbus: both models, one write per store")`.
  - `test("use_virtues off runs none of the three")`.
- [ ] **Step 2: Run and confirm failure.** `nf-test test tests/virtues.nf.test`
- [ ] **Step 3: Implement.** If Task 1 found that backsub drops unknown columns, stop here and
      report before choosing how to carry `uniprot_id` past it.
- [ ] **Step 4: Run.** `nf-test test --tag stub && nf-core pipelines lint`
      Expected: pass; no new lint failures.
- [ ] **Step 5: Re-render the metro map** (`docs/CONTRIBUTING.md#metro-map`); list it in the final
      report for the user to look at.
- [ ] **Step 6: Commit.** `Wire VirTues into LEARNED_FEATURES`

### Task 9: Documentation and release notes

**Files:**

- Modify: `docs/usage.md`, `docs/output.md`, `docs/decisions.md`, `CITATIONS.md`, `CHANGELOG.md`,
  `ROADMAP.md`, `site/myst.yml`.
- Create: `site/modules/virtues.md`; an example marker sheet with `uniprot_id` under `assets/`
  if one exists for Nimbus, else in the page.

- [ ] **Step 1: Write the docs** listed in the spec's "Docs and release", in plain language for
      `site/`. `docs/output.md` gets a snippet:

  ```python
  sdata["cellpose_virtues"].X  # cells x 512, float16
  ```

- [ ] **Step 2: Release notes.** `CHANGELOG.md`: VirTues under Added in the next minor release
      (`## v3.3.0 - [unreleased]` unless `nextflow.config` shows 3.2.0 still unreleased; then
      under 3.2.0). `ROADMAP.md`: VirTues out of 3.4, KRONOS stays; add QC plots, per-tile tasks, a
      crop-step parameter, pre-stitched input. `CITATIONS.md`: VirTues, ESM-2, UniProt, spora; the
      `sp32` CC BY-NC 4.0 licence.
- [ ] **Step 3: Build.** `site/build.sh && prek run --all-files`. Expected: no broken links; clean.
- [ ] **Step 4: Commit.** `Document VirTues embeddings`

### Task 10: QC chapter (cuttable)

**Files:**

- Modify: `bin/qc_metrics.py`, `bin/qc_report.py`, `conf/modules.config` (`QC_METRICS` ext.args
  adds `--virtues-table ${meta.method}_virtues` when `params.use_virtues`).
- Test: `tests/unit/qc/test_qc_metrics.py`, `tests/unit/qc/test_qc_report.py`.

**Interfaces:**

- Produces: `virtues_metrics(uns: dict, method: str) -> dict`: channels used, `unembedded`, the
  statistics per marker, cells embedded and without a pixel for `method`, squares kept and dropped.
- Produces: `virtues_section(v: dict) -> str`, facts only; `build` appends it when `"virtues" in
metrics`.

- [ ] **Step 1: Write the failing tests**: the metrics from a hand-made `uns`; the report has
      "VirTues" when present and not when absent.
- [ ] **Step 2: Run and confirm failure.** `pytest tests/unit/qc -q`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** `pytest tests/unit -q && nf-test test --tag stub`
- [ ] **Step 5: Commit.** `QC: VirTues facts`

### Task 11: Cluster checks

No code. Write each command for the user, who submits it; record results in the SDD ledger and the
final report.

- [ ] **Step 1: Model tests and parity.** `pytest tests/unit/test_virtues_model.py` and
      `tools/virtues_parity.py` in the image on an A40.
      **Gate.** Pass when ours vs upstream is within upstream vs itself; if upstream vs itself is
      exactly zero, when every cell's cosine is ≥ 0.999 (report the max abs difference). Otherwise
      stop and report the numbers; do not loosen the bar.
- [ ] **Step 2: Exemplar-001** with `use_virtues`, `use_gpu`, `use_tissue_segmentation`, the same
      run twice (determinism within the parity bar), peak memory and `VIRTUES` time from the
      trace, crops per second.
- [ ] **Step 3: Backsub comparison.** Exemplar-001 with and without `use_backsub`; per-cell cosine
      of the same cells (matched by `cell_id`), reported without a threshold.
- [ ] **Step 4: Sizing.** From Step 2, propose `VIRTUES` time and memory in `conf/base.config`.
