# 3.4: learned features, VirTues

ROADMAP "3.4 onward". VirTues is the second model in the `LEARNED_FEATURES` stage that Nimbus
added ([Nimbus design](2026-11-11-learned-features-nimbus-design.md)). It gives every segmented
cell, every 128 µm tissue square and every core or slide a 512-number embedding from a spatial
proteomics foundation model, so cells and regions can be clustered, compared across patients and
fed to classifiers.

## Goal

With `use_virtues`, each store gains:

- `{method}_virtues`: one row per cell, the same rows as `{method}_table`, 512 columns.
- `virtues_niches` (squares) with `virtues_niches_table`: one row per 128 × 128 µm tissue square.
- `virtues_tissue`: one row per store (a core on a TMA, the image otherwise).

Success for this release is engineering only; usefulness on real data is judged afterwards (see
"After the build"):

- pytest and the stub nf-tests pass, with VirTues on and off and on a TMA.
- **Parity:** on the example core bundled in the VirTues repository, our runner's cell embeddings
  differ from upstream `compute_cell_tokens` by no more than upstream differs from itself when only
  its batch size (`chunk_size`) changes, both measured on the cluster GPU. If upstream's own
  difference is zero (FlashAttention keeps crops apart, so it may be), the bar is a per-cell cosine
  similarity of at least 0.999, with the largest absolute difference reported. Worse comes back to
  you.
- Two GPU runs give the same embeddings within that same bar.
- The statistics computed from histograms equal a direct numpy computation.
- Peak memory does not grow with image size.

## Findings that shape the design

Read on 2026-11-24: `bunnelab/virtues` at `d2c25e1`, `bunnelab/spora-io`, HF `bunnelab/virtues`,
arXiv 2501.06039v2 and 2610.24002 (spora), spora docs. The Nature paper (s41586-026-10884-y) is
paywalled and was not read.

- **Licences.** Code MIT. Weights ungated: `sp32` CC BY-NC 4.0 (the authors' academic default and
  the benchmarked model), `sp31` MIT, `imc14` CC BY-NC 4.0. spora-bench is CC BY-NC-ND: do not
  adapt its code.
- **GPU only.** `flash_attn.flash_attn_varlen_qkvpacked_func` is imported unconditionally. No CPU
  path, no Mac path. The cluster's A40s (Ampere) support FlashAttention 2.
- **Model.** `sp32/model.safetensors`: 43.4 M parameters (encoder 34.6 M), float32, 174 MB.
  `model_dim` 512, patch 8 px, crops 128 px. Upstream inference runs under fp16 autocast.
- **Marker identity.** Each channel needs a UniProt ID (isoform suffix allowed, e.g. `P08575-8`).
  Its sequence is embedded by ESM-2 `esm2_t30_150M_UR50D`. The embeddings are a non-persistent
  buffer, so any panel works without retraining.
- **DNA stains are not embedded upstream.** In the bundled example, `Iridium` channels have no ID
  and are left out; a Histone H3 _antibody_ is embedded as `P68431`.
- **Resolution.** spora resamples every dataset to 1.0 µm/px. The resampling method for
  multiplex images is not published.
- **Intensity recipe** (spora-io `std.py`, `standardize.py`): over tissue pixels only (a tissue
  mask), clip each channel at its 0.99 quantile, `log1p`, z-score with mean and SD, then at
  inference a 3 × 3 Gaussian blur (sigma 1). Statistics are computed before the blur. SD is the
  population SD (from sum, sum of squares and count). The released weights were trained with the
  cap **per image** (an IMC region, about a core) and mean and SD **per dataset**, often hundreds
  of slides (`quantile_clipping_log1p/uq_0.99_image`, `stats_level="global"`). Per-slide
  statistics (settled below) therefore depart from training; `virtues_stats` is the way back to
  dataset-wide statistics.
- **Cell embeddings** (`virtues/utils/cell_tokens.py`): the image (padded by 120 px of zeros
  before standardisation) is cut into 128 px crops every 42 px, plus extra crops flush with the
  bottom and right edges. Each crop's 16 × 16 patch embeddings are averaged into each cell,
  weighted by the cell's pixel count in each patch. Upstream keeps every crop's embeddings in
  memory (~120 GB for a 2 × 2 cm slide) and loops in Python.
- **Crops are independent.** Attention never crosses crops, so a crop's embeddings depend only on
  its own pixels.
- **Niche and tissue embeddings** (paper): niche = mean of a non-overlapping 128 px crop's patch
  embeddings, crops under 30% tissue skipped; tissue = mean over all patches.

## Approaches

1. **Call upstream `compute_cell_tokens` per store.** Least code; memory grows with the image.
   Rejected.
2. **Convert stores to spora format and run their tools.** Closest to upstream; copies every image
   a second time, and the whole-dataset tool is CC BY-NC-ND. Rejected.
3. **Our tiled runner, one GPU task per store. Chosen.** Upstream's encoder is called unchanged;
   only the averaging into cells, squares and tissue is ours, and parity checks it against 1.
4. **3 with one task per tile, then a gather.** Multiplies SLURM jobs. Deferred: 3's tile function
   is the unit it would call.

## Settled with you (2026-11-24)

1. Statistics per **slide**, per marker, one set per input image; on a TMA all cores of a slide
   share them. A deliberate break from Nimbus's per-core choice: cells stay comparable across
   cores and patients.
2. Statistics over **tissue pixels** from `use_tissue_segmentation`, which `use_virtues` requires.
3. The 0.99 clip is per slide too, like mean and SD.
4. `virtues_stats` (advanced): one statistics file applied to every slide of a run, for freezing a
   rerun or normalising a cohort.
5. Cell, niche **and** tissue embeddings.
6. Niches are squares (shapes) with a table.
7. A channel is embedded **if and only if** its marker-sheet row has a `uniprot_id`. No parameter.
8. DNA stains are never embedded; no Histone H3 mapping.
9. Weights: `sp32`.
10. Cells only, no nuclei, like upstream.
11. Embeddings stored as float16.
12. QC: facts only for now; plots after real-data validation.
13. Approach 3, on the condition that its cell embeddings match upstream within GPU rounding noise.
14. Usefulness on published and in-house data is tested after the build, in a separate
    conversation.
15. `use_virtues` requires `use_gpu`, so the whole run is on GPU, segmentation included. Accepted:
    simpler, faster; outlines differ slightly from a CPU run, and InstanSeg's GPU channel limit
    applies (raising it from 10 to 15 is a separate change).
16. `use_virtues` requires `use_preprocessing`: pre-stitched input has no marker sheet. Support for
    it goes on the ROADMAP.

## Parameters and the marker sheet

**Learned features group:**

| Parameter       | Type, default    | Meaning                                                                       |
| --------------- | ---------------- | ----------------------------------------------------------------------------- |
| `use_virtues`   | boolean, `false` | Embed cells, 128 µm tissue squares and each core or slide with VirTues.       |
| `virtues_stats` | path, unset      | Advanced. A `virtues_stats.json` from an earlier run, applied to every slide. |

`use_gpu` gives each `VIRTUES` task a GPU.

**Marker sheet:** a new optional column `uniprot_id`. The schema checks the UniProt accession
format with an optional isoform suffix (`-N`), so a marker name typed into it is caught.

**Validation** (`validateParams`, each with its own message). The run stops when `use_virtues`
is set and:

- `use_gpu` is off (FlashAttention has no CPU path);
- `use_preprocessing` is off (no marker sheet, so no UniProt IDs);
- `use_tissue_segmentation` is off;
- `segment_cells` is off;
- `pixel_size` is unset;
- no marker-sheet row has a `uniprot_id`;
- a `dna`-role row has a `uniprot_id` ("DNA stains are not embedded");
- two rows share a `uniprot_id`;
- `virtues_stats` lacks a marker that would be embedded, or records a different `uniprot_id` for it.

`virtues_stats` without `use_virtues` stops too. An ID with a valid format but absent from the
bundled UniProt sequences fails the task, naming the ID.

## Specs

`featureSpecs` gains:

```groovy
[name: 'virtues', model: 'virtues', channels: null, pixel_size: pixelSize(args), stats: path or null]
```

`LEARNED_FEATURES` resolves `channels` per sample from the marker sheet as
`[[marker_name, uniprot_id], ...]`, in sheet order.

## Graph

```text
SEGMENTATION.out.sdata ─► VIRTUES_HISTOGRAM (per store)
                              │ grouped by meta.slide ?: meta.sample
                          VIRTUES_STATS (per slide) ─► virtues_stats.json (published)
                              │ joined on slide
SEGMENTATION.out.sdata ─► VIRTUES (per store, every method at once) ─► WRITE_FEATURES (per store)
```

- With `virtues_stats`, the two statistics tasks are skipped and the file goes to every store.
- **Histograms read the store after segmentation**, not alongside it, so no task reads a store
  another task is mutating. They are cheap next to `VIRTUES`.
- **One `VIRTUES` task per store, not per method.** The GPU pass does not depend on cell masks;
  only the averaging does, and it is repeated per method in the same task.
- `WRITE_FEATURES` remains the only writer in the stage.

## Statistics

`VIRTUES_HISTOGRAM` (CPU) reads the image at model scale (below) and `region_of_interest`,
rasterised at 1 µm/px (pixel centre inside a polygon). Per embedded marker it writes the histogram
of tissue-pixel values rounded to integers (an error under half a count). Rounding applies only to
the histogram; the model sees unrounded values.

`VIRTUES_STATS` sums a slide's histograms and computes, per marker:

- `cap`: the 0.99 quantile, equal to `numpy.quantile(pixels, 0.99)` with numpy's default method;
- `mean`, `sd`: of `log1p(min(x, cap))` over tissue pixels, population SD;
- `tissue_pixels`.

`virtues_stats.json`: format version, slide, cores, model pixel size, and per marker name the
`uniprot_id`, `cap`, `mean`, `sd`, `tissue_pixels`. Published to `learned_features/` and copied
into every table's `uns`.

Histograms assume an integer image (Ashlar writes uint16). If the image is not integer at this
point (e.g. after backsub), the plan stops and checks in.

## The tiled runner

`bin/virtues_cells.py`. Pure functions are tested with a fake encoder.

**Model scale, without a temporary image.** The image is resampled to 1 µm/px by separable
area-weighted averaging. Weights come from global pixel coordinates only, so any window with
enough input context computes identical values. The histogram task and `VIRTUES` share this
function. No resampled copy is written.

**Input.** Per window: resample, standardise with the slide statistics (clip, `log1p`, z-score),
then blur, with upstream's 120 px zero padding at the true image edge and blur context from
neighbouring pixels elsewhere.

**Cells.**

- The crop grid is upstream's `_get_uniform_crops` applied once to the padded whole image.
- Cells are rasterised at 1 µm/px (pixel centre rule, deterministic order for overlaps). A cell is
  owned by the 2048 px tile holding its centroid.
- A window embeds every global crop that touches its owned cells, so every cell sees exactly
  upstream's crop set. Crops on tile borders are embedded by both neighbours; that is accepted
  overhead.
- Per cell, the sums of weighted patch embeddings and weights are accumulated in float32, then
  divided. A cell with no pixel at 1 µm/px gets a NaN row and is counted in QC.

**Niches.** A separate pass over non-overlapping 128 px crops on a grid from the image origin.
Squares not fully inside the image are dropped. A square is kept when at least 30% of its pixels
are inside `region_of_interest`. Its embedding is the mean of its 256 patch embeddings.

**Tissue.** The mean of the kept squares' embeddings, which equals the mean over their patches.

**Marker embeddings.** Computed in the task from the bundled UniProt sequences with ESM-2, using
upstream's `compute_esm_embeddings` functions unchanged.

**Device.** CUDA from `task.accelerator`, checked as in `NIMBUS`. fp16 autocast as upstream.

## Outputs

- **`{method}_virtues`:** `TableModel` annotating `{method}_cells`, rows identical to
  `{method}_table`. `X` float16, cells × 512; `var_names` `virtues_0` … `virtues_511`; `obs`
  copied (`region`, `slide`, `core_id`, `cell_id`).
- **`virtues_niches`:** square polygons, in the image's coordinate system.
  **`virtues_niches_table`:** annotates them; `X` float16, squares × 512; `obs` with
  `tissue_fraction`.
- **`virtues_tissue`:** one row, `X` float16 1 × 512, `obs` `slide`, `core_id`, `n_niches`. No
  region annotation: one vector per store does not map onto `region_of_interest`'s polygons.
- **`uns['virtues']`** on each: commit, weights file and sha256, ESM-2 model, UniProt release,
  channels used and channels without an ID, the statistics, pixel size, crop size and step,
  padding, tile size, device, counts.
- **Published:** `virtues_stats.json` per slide; a provenance JSON per store.

## Writer and merge

- `WRITE_FEATURES` also writes shapes, and accepts tables that are not per method: their rows
  must match the shapes they annotate (`virtues_niches_table`), or there is no check
  (`virtues_tissue`). It still removes each element by path before writing.
- `bin/write_segmentations.py`: `virtues` joins `LEARNED_MODELS`, and `virtues_niches`,
  `virtues_niches_table` and `virtues_tissue` become pipeline-owned, so a rewrite removes stale
  ones.
- `bin/merge_spatialdata.py`: tables without a region annotation are copied and renamed per
  core, like the others. Today an unannotated table raises.

## Container

The plan's first task is a spike, a gate as for Nimbus. Image `docker.io/josenimo/virtues:<tag>`
in `tools/containers/virtues/`:

- a CUDA PyTorch base with a matching prebuilt FlashAttention 2 wheel, plus spatialdata;
- `virtues` at the pinned commit;
- baked: `sp32/model.safetensors`, ESM-2 150M weights, the UniProt human Swiss-Prot sequences
  with isoforms (release recorded);
- `HF_HUB_OFFLINE=1`, no network at run time.

It passes when the image imports `virtues`, `flash_attn` and spatialdata, loads the weights, and
runs the bundled notebook's cell-embedding cell on a cluster GPU. If it cannot be built, it comes
back to you. Listed in `containers.tsv` and the manifest; staged as the other images are.

## Resources

- `VIRTUES`: one A40, memory flat (one window at a time, crops batched on the GPU). Time is
  unmeasured; estimate ~3 h for a 5 × 5 cm slide at 40 markers. The first cluster run measures
  crops per second, and sizing follows.
- `VIRTUES_HISTOGRAM`: CPU, `process_low`. `VIRTUES_STATS`: `process_single`.
- `conf/gpu.config` adds `VIRTUES` to the accelerator selector; `maxForks` applies.
- Jobs: one `VIRTUES` and one histogram task per store, one statistics task per slide.

## QC

A facts-only chapter in `_qc.json` and the report:

- channels used and channels without an ID;
- the slide statistics per marker;
- cells embedded, and cells with no pixel at 1 µm/px;
- squares kept and dropped.

Last task, so it can be cut.

## Tests

**pytest** (`tests/unit/test_virtues_cells.py`, `test_virtues_stats.py`, writer and merge tests),
with a fake encoder whose patch embedding is the patch's mean input, so results are
hand-computable:

- the crop grid equals upstream `_get_uniform_crops`;
- every cell is owned once; tiled equals whole-image exactly, for any tile size;
- resampling is window-independent, bit for bit;
- histogram statistics equal numpy on the pooled pixels;
- the niche grid, the 30% rule, and tissue = mean of the kept squares;
- writer: shapes and the new tables, idempotent; stale elements removed; merge copies the
  unannotated table.

**nf-test:** stub runs with VirTues on (one method, two methods, a TMA with stats grouped per
slide, `virtues_stats` given) and off (graph unchanged); each validation rule.

**Cluster** (I propose the commands, you submit):

- the container spike;
- parity on the bundled example core, its own mask and statistics supplied through the
  `virtues_stats` format;
- determinism: the same core twice;
- exemplar-001 end to end, peak memory recorded;
- exemplar-001 with and without backsub, reporting how far the same cells' embeddings move. No
  threshold; it feeds the real-data conversation.

## Docs and release

- `docs/usage.md`: the `uniprot_id` column with an example, DNA not embedded, the GPU and tissue
  requirements, `virtues_stats`.
- `docs/output.md`: the three tables and the squares, how to read them, the `uns` keys.
- `docs/decisions.md`, "Learned features": slide statistics over tissue and why; one task per
  store; the global crop grid and why tiles match upstream; DNA not embedded; float16; `sp32`.
- The `site/` module page in plain language; an example marker sheet with `uniprot_id`.
- `CITATIONS.md`: VirTues, ESM-2, UniProt, spora; the `sp32` licence.
- `CHANGELOG.md`: Added, in the next minor release.
- `ROADMAP.md`: VirTues out of 3.4, KRONOS stays; new items: QC plots, per-tile tasks, a crop-step
  parameter, pre-stitched input.
- `containers.tsv`, and the metro map re-rendered for a human to check.

## Out of scope

Marker reconstruction and inpainting; the segmentation head; nuclei; `sp31` and `imc14`;
fine-tuning; QC plots; per-tile tasks; a crop-step parameter; pre-stitched input; raising
InstanSeg's GPU channel limit; KRONOS.

## After the build

A conversation with you on real-data validation: which datasets (published Orion
`lin2023high` and IF `klein2026explainable` from spora, your trusted annotated sets) and what
result counts as useful, e.g. a linear classifier on embeddings against one on mean intensities,
split by patient.
