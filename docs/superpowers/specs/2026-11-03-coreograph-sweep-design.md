# Coreograph downsample sweep

Users run Coreograph blind with `--downsampleFactor 5`, and a wrong factor ruins every
downstream step. Instead, the pipeline asks how many cores and how large, tries several factors
in detection only, and dearrays once with the best.

## Goal

One run: detect cores at k = 3…7 in parallel, score each against the user's expectation, run
the real `COREOGRAPH` once with the winning k. No core tiles are written during the sweep.

Success: on exemplar-002 the sweep picks k = 4 (or a neighbour finding the same 4 cores at the
right size), and its k = 4 core labels equal `COREOGRAPH`'s `coremask` pixel for pixel.

## Findings that shape the design

From `UNetCoreograph.py` at 2.4.6:

- **Detection and tiling are separable.** Lines 963–1099 read one channel, halve it k times
  (`getProbMaps`), run the UNet, then threshold, `blob_log` and watershed into a label image.
  Everything after line 1105 writes each core at full resolution and segments it with active
  contours: the expensive part.
- **The script imports cleanly.** It has a `__main__` guard; `getProbMaps` and `UNet2D` are
  module-level. MIT licence, so the TMA-mode block can be copied with attribution.
- **One merged blob inflates every crop.** Crop size is uniform, from the 99th percentile of
  core area × 1.2 × `--buffer`.
- **`Coremask.tif` is `uint8`.** Labels wrap above 255 cores.
- **Coreograph reads the whole channel eagerly** (`tifffile.imread`), which our
  `no-eager-image-reads` hook forbids in `bin/`. Its k nearest-neighbour halvings map output
  pixel i to input 2^k·i (cv2 `INTER_NEAREST` maps x to ⌊x·src/dst⌋ = 2x), so a strided zarr
  read `[::2^k, ::2^k]`, cropped to ⌊shape/2^k⌋, gives the same image. Then `getProbMaps(I, 0)`
  skips its own halving. The exemplar-002 equality check confirms this.

From the dearray-first spike (`PY46_coreograph_test`, `DEARRAY_FIRST_INTEGRATION.md` §4.4):

- **Detection is scale-sensitive and fails silently.** On exemplar-002, 4 cores at 6.4–9.0
  µm/px; one glandular core splits into 2–3 below ~6.2 µm/px, and Coreograph exits 0. At
  0.65 µm/px, k = 3 is 5.2 µm/px (in the split zone), k = 4 is 10.4, the default k = 5 is 20.8.
- **Coreograph 2.4.6 runs natively on Apple silicon** (TF 2.21 arm64 wheels), unlike its
  amd64-only image. The spike's `.venv-coreograph`, `vendor/UNetCoreograph` (2.4.6) and
  `out/baseline/wsi_allcycles.ome.tif` let the detect script be checked against real
  Coreograph on the Mac.
- Dearray before Ashlar is a separate spec. It reuses detect and select on a nominal mosaic.

## Parameters

Schema via `nf-core pipelines schema build` only.

- `tma_expected_cores` (integer): total cores expected on the slide. A count, not rows × cols:
  arrays have empty or lost positions, and users know the count from the TMA map.
- `tma_core_diameter_mm` (number): expected core diameter.
- `coreograph_args`: default becomes empty. Setting it is the opt-in manual mode: no sweep,
  `COREOGRAPH` runs with exactly these args, as today.
- Factors are not a parameter. The pipeline sweeps k = 3…7.

Startup validation, when `use_tma_dearray`:

- Sweep mode (`coreograph_args` empty): both `tma_*` params required; the error names both and
  mentions `coreograph_args` as the manual alternative.
- The sweep runs Coreograph's defaults: `--channel 0 --buffer 2 --sensitivity 0.3`. The
  existing reference-DNA check already defaults to index 0, so it still applies. A user whose
  nuclear stain is not channel 0 uses manual mode.

## Scripts

`bin/coreograph_detect.py`, one call per `(slide, k)`, in `unetcoreograph:2.4.6`:

- Args: `--image --downsample-factor --channel --sensitivity --buffer --expected-cores
--core-diameter-mm --prefix`.
- Reads the channel lazily (`TiffFile(...).aszarr()`, strided as above) and the pixel size
  with `ome_types`, as Coreograph does. No pixel size in the OME-XML: fail with a message,
  since the diameter cannot be compared without it.
- TMA-mode block copied verbatim, with an MIT and source-commit header. Stops at the labels.
- TensorFlow is imported inside the detect function only; metrics and overlay are plain
  numpy/skimage and testable without the container.
- Writes `{prefix}_k{k}_metrics.json`, `{prefix}_k{k}_coremask.tif` (`uint16`),
  `{prefix}_k{k}_overlay.png` (outlines and numbers on a thumbnail).

Metrics per k:

| metric         | definition                                                   |
| -------------- | ------------------------------------------------------------ |
| `n_cores`      | detected labels                                              |
| `count_error`  | \|n − N\| / N                                                |
| `diam_mm`      | median 2√(area/π), scaled by pixel size × 2^k                |
| `diam_error`   | \|diam_mm − D\| / D                                          |
| `size_cv`      | std / mean of core areas; merges and splits                  |
| `crop_ratio`   | Coreograph's would-be crop size / D; one merged blob         |
| `core_px_at_k` | D / pixel size / 2^k; the core size the UNet sees, reference |
| `um_per_px`    | pixel size × 2^k; the scale the UNet sees, reference         |

Score = `count_error + diam_error + size_cv`, lowest wins. Zero cores scores infinity. Ties go
to the smaller k (more resolution). Weights change only if real TMAs show a wrong pick.

`bin/coreograph_select.py`, one call per slide, same image:

- Reads all metrics JSONs; writes `{slide}_sweep.tsv` sorted by score,
  `{slide}_sweep_overlays.png` side by side, and `selected_k.txt`.
- Never fails the run. If the winner has `count_error > 0.1` or `diam_error > 0.25`, it warns
  in the log and in a TSV column.

## Graph

In `PREPROCESS_IMAGES`, when `use_tma_dearray` and `coreograph_args` is empty:

```
ASHLAR.out.tif ─combine─ [3..7] ─> COREOGRAPH_DETECT      slide × k
                                     │ groupTuple(size: 5)
                                     v
                                  COREOGRAPH_SELECT        per slide ─> [meta, k]
ASHLAR.out.tif ─join─────────────────┘
   └─> [meta + [downsample_factor: k], image] ─> COREOGRAPH  (module unchanged)
```

- k reaches Coreograph through meta. `conf/modules.config` builds args per task:
  sweep mode `"--channel 0 --buffer 2 --downsampleFactor ${meta.downsample_factor}"`,
  manual mode `params.coreograph_args`.
- Cores inherit `downsample_factor` in their meta, so each records the k that produced it.
- Manual mode: the graph is today's, unchanged.

New modules in `modules/local/`: `coreograph_detect`, `coreograph_select`, both with stubs,
both on the existing `unetcoreograph:2.4.6` image (nothing new to stage).

## Outputs

`preprocessing/dearray/sweep/`: per slide the TSV, the overlay panel, and each k's metrics JSON
and core labels.

## Testing

- pytest (Mac): metrics on synthetic label images with known count and diameter; a merged
  blob; zero cores; the tie-break; the warning thresholds.
- Native on the Mac, before any cluster run: the detect script at k = 4 on the spike's
  exemplar-002 whole-slide image gives the same centroids as `UNetCoreograph.py` itself.
  A local check, not a committed test.
- Stub nf-test: sweep mode gives 5 detect, 1 select, 1 `COREOGRAPH` per slide; manual mode
  gives no detect or select; missing `tma_*` params fail at startup.
- `test_exemplar002` on the cluster, its `coreograph_args` removed: N = 4, D = 1.5 mm
  (measured by the user, not from Coreograph). Assert the selected k and that the k = 4 labels equal `COREOGRAPH`'s `coremask`.
- Later: the user's larger TMA subsets, which also exercise `size_cv` and `crop_ratio`.

## Housekeeping

`sizes.config` entries for both processes (detect starts at `COREOGRAPH`'s size, refit after
the cluster run); `usage.md`; `CHANGELOG` (breaking: TMA runs now need `tma_*` params or
`coreograph_args`); `CITATIONS` unchanged; re-render the metro map with `--animate` (dots
travel each path) for a human to check.

Before the sweep, a separate commit: agents may hand-edit `nextflow_schema.json`. `CLAUDE.md`
and `CONTRIBUTING` say so, and hooks lint the schema after each agent edit
(`.claude/settings.json`) and at commit (prek).

## Not now

- The core segmentation as GeoJSON shapes in the SpatialData.
- The overlay panel in the QC report.
- Choosing the sweep channel from the marker sheet's `dna` role instead of index 0.
- Sweeping `--sensitivity` or `--buffer`.
