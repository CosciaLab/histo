# H&E registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a same-section H&E, given per sample, is registered onto Ashlar's stitched IF by `valis_pipeline` and added
to the sample's store as `{sample}_he`, with its maps and QC published.

**Architecture:** `REGISTER_HE` runs `valis_pipeline` in its own image on `ASHLAR.out.tif` and the H&E, in parallel
with backsub and segmentation. `ADD_REGISTERED_IMAGE`, a single writer in the sopa image, adds the moved H&E after
`SEGMENTATION` and before QC. The QC report reads the run's `qc/summary.csv`.

**Tech Stack:** Nextflow DSL2, nf-schema, nf-test; Python (spatialdata, tifffile, dask) with pytest via
`uv run --frozen --group dev`; images `docker.io/josenimo/sopa:2.3.0` (existing) and
`docker.io/leventetn/valis_pipeline:<version>` (new, from `valis_pipeline` docs/superpowers/plans/2026-11-10-histo-container.md).

**Spec:** `docs/superpowers/specs/2026-11-10-he-registration-design.md`. Read it first.

## Global Constraints

- Read CLAUDE.md. Branch `feat/he-registration` off `dev`; never push. Commit titles under ~60 chars, ending with the
  `Co-Authored-By` line.
- Off by default: a run without `use_he_registration` must produce byte-identical stores and the same task list.
- Element name `{sample}_he`; channels `r`, `g`, `b`; uint8; `Identity` to `global`. Store attribute key
  `he_registration`. Published folder `preprocessing/he_registration/{sample}/`.
- The registration channel index refers to Ashlar's image: compute it from the sample's original marker sheet
  (`dearrayChannel`), never from backsub's renumbered sheet.
- Fixed VALIS settings in the module script: `valis: {processed_px: 1000, non_rigid_px: 4000, non_rigid: deepflow}`,
  `same_section: true`, `inverse: invert`, `spatialdata_mode: none`.
- `bin/` scripts import heavy libraries inside functions. No `tifffile.imread` in `bin/` (hook).
- Edit `nextflow_schema.json` by hand; never `assets/params_template*.yml`.
- Run before each commit: `prek`, `uv run --frozen --group dev pytest tests/unit`,
  `nf-test test --tag stub,validation` (the last from Task 5 on).
- Tasks 1, 2, 4 and 7 need no image; Task 3 needs the image only for its real run (the stub does not).

## Review Focus

1. **A sample without `he_image` in a run with `use_he_registration`**: runs as today, no `REGISTER_HE` task, store
   unchanged, one log line. Test in Task 5.
2. **Backsub drops a channel before the first `dna`**: the index passed to `REGISTER_HE` still names the `dna` channel of
   Ashlar's image. Test in Task 5.
3. **The moved H&E and the store image differ in height or width**: `ADD_REGISTERED_IMAGE` fails naming both shapes.
   Test in Task 4.
4. **`-resume` after the registration finished and segmentation failed**: `REGISTER_HE` is cached; the writer runs once
   segmentation succeeds. Check in Task 8.
5. **An ambiguous placement with `he_placement_check: stop`**: the task fails naming `qc/placement.jpg`, the rest of
   the sample's run is not blocked until the writer. Check in Task 8 with a rotated crop.

---

### Task 1: `he_image` samplesheet column

**Files:**

- Modify: `assets/schema_input_cycle.json`, `assets/schema_input.json` (new last property, optional, `format:
  file-path`, `exists: true`, pattern `\.(svs|czi|ome\.tiff?)$`)
- Modify: `subworkflows/local/utils_nfcore_histo_pipeline/main.nf` (equal on a sample's rows, like
  `validateMarkerSheetColumn`; emit `[[id: sample], file]` or nothing)
- Test: `tests/validate_marker_sheet_column.nf.test` (new cases, same pattern), placeholder `.svs` files in
  `tests/stub_data/`

- [ ] **Step 1:** failing validation tests: two rows of one sample with different `he_image` fail naming the sample; an
  unknown extension fails; a sheet without the column still passes.
- [ ] **Step 2:** add the property last; positional indexes (`:117, 229, 266, 278`) unchanged; new index for
  `he_image` read by name where possible.
- [ ] **Step 3:** emit `ch_he_images` from `PIPELINE_INITIALISATION`; `main.nf` passes it to `HISTO`.
- [ ] **Step 4:** run checks; commit `samplesheet: optional he_image column`.

### Task 2: parameters

**Files:**

- Modify: `nextflow.config` (defaults), `nextflow_schema.json` (new group "H&E registration"),
  `subworkflows/local/utils_nfcore_histo_pipeline/main.nf` (`validateParams`)
- Test: `tests/he_registration_params.nf.test` (new; pattern of `tests/reject_unknown_params.nf.test`)

- [ ] **Step 1:** failing tests: `use_he_registration` with `use_tma_dearray` fails ("TMA slides are not supported
  yet"); with `preprocessing_only` fails; `he_placement: landmarks` rejected by the schema enum; `he_micro_um: 0`
  rejected.
- [ ] **Step 2:** `use_he_registration` (false), `he_placement` (`search` | `none`), `he_placement_check` (`stop` |
  `skip`), `he_micro_um` (string: `native` or a positive number, parsed with `toNumber`). Help text in the
  "**Ignored unless:** / **Requires:**" style.
- [ ] **Step 3:** run checks (prek regenerates the params templates); commit `params: H&E registration`.

### Task 3: `REGISTER_HE` module

**Files:**

- Create: `modules/local/register_he/main.nf`, `modules/local/register_he/meta.yml`
- Create: `bin/he_registration_config.py` (writes `config.yml` from arguments; pure function `build_config`)
- Modify: `conf/modules.config` (publishDir `preprocessing/he_registration/`), `conf/sizes.config` (resources),
  `containers.tsv` (via `tools/container_manifest.py`)
- Test: `tests/unit/test_he_registration_config.py`, `tests/he_registration.nf.test` (stub; pattern of
  `tests/preprocess_images.nf.test`)

**Interfaces:**

- Input: `tuple val(meta), path(ifimage), path(heimage)`, `val channel_index`.
- Output: `run` = `tuple val(meta), path("${meta.id}")`; `image` = `tuple val(meta), path("${meta.id}_he.ome.tif")`;
  `qc` = `tuple val(meta), path("${meta.id}/qc/summary.csv")`; versions to the `versions` topic (valis-wsi from
  `registration.json`, valis_pipeline commit).
- `build_config(name, ifimage, channel_index, heimage, placement, placement_check, micro_um) -> dict` with the fixed
  settings of Global Constraints, `outdir: "."` and image names `if` (reference) and `he` (moving), so step 5 writes
  `spatialdata/he_on_if.ome.tif`.

- [ ] **Step 1:** failing pytest for `build_config`: fixed keys present, `micro_um` number or `native`, paths absolute.
- [ ] **Step 2:** implement; module script: `he_registration_config.py ... > config.yml`, then
  `python /opt/valis_pipeline/scripts/run.py config.yml`, then move `${meta.id}/spatialdata/he_on_if.ome.tif` to
  `${meta.id}_he.ome.tif` and delete `${meta.id}/valis/`.
- [ ] **Step 3:** stub writes the folder layout, `qc/summary.csv` header, `placement.json` `{}` and a 1 × 1 RGB OME-TIFF
  (`tests/stub_bin` shim if a tool is needed); stub nf-test passes.
- [ ] **Step 4:** resources: `process_high`-like defaults (8 CPUs, 64 GB, 12 h), `size_huge` 256 GB, retry on
  exit 137 with memory doubled once.
- [ ] **Step 5:** run checks; commit `register_he: valis_pipeline on the stitched IF`.

### Task 4: `ADD_REGISTERED_IMAGE` writer

**Files:**

- Create: `modules/local/add_registered_image/main.nf`, `bin/add_registered_image.py`
- Test: `tests/unit/test_add_registered_image.py`

**Interfaces:**

- `add_registered_image(store: Path, tif: Path, run_dir: Path, name: str) -> None`: reads the OME-TIFF lazily (tifffile
  `aszarr` + dask), parses `Image2DModel` with `c_coords=["r", "g", "b"]`, `Identity`, the same pyramid scale factors as
  the store image, writes the element, then `he_registration` group attributes from `run_dir/registration.json`,
  `placement.json` and `qc/summary.csv`.

- [ ] **Step 1:** failing tests on a synthetic store (one 256 × 256 image element): element added with 3 channels and
  Identity; existing `{sample}_he` refused; 255 × 256 TIFF fails naming both shapes; attributes hold commit, map
  stage and gap; `cell_segmentation_image` unchanged.
- [ ] **Step 2:** implement; reuse the store-attribute writing of `bin/set_channel_names.py`.
- [ ] **Step 3:** module (sopa image), stub copies the store and touches a marker file; run checks; commit
  `add_registered_image: H&E into the store`.

### Task 5: wiring

**Files:**

- Modify: `subworkflows/local/preprocess_images/main.nf` (`REGISTER_HE` on `ASHLAR.out.tif` joined with `he_image` and
  `dearrayChannel` of the original sheet; emit `he_registration` and `he_image`)
- Modify: `workflows/histo.nf` (pre-stitched path: `REGISTER_HE` on the supplied image; `ADD_REGISTERED_IMAGE` between
  `SEGMENTATION` and QC/`PUBLISH_SPATIALDATA`, samples without H&E joined with `remainder: true` and passed through)
- Test: `tests/he_registration.nf.test` (more stub cases; two samples as in `tests/two_methods.nf.test`)

- [ ] **Step 1:** failing stub tests: two samples, one with `he_image`: one `REGISTER_HE` task, one writer task, both
  stores published; backsub with a removed channel before `dna`: index unchanged; `use_he_registration` false with an
  `he_image` column: no new tasks.
- [ ] **Step 2:** implement; comment in one line why the writer sits before QC (nothing writes after it).
- [ ] **Step 3:** run checks; commit `histo: register H&E after Ashlar, add after segmentation`.

### Task 6: publishing and docs of outputs

**Files:** `conf/modules.config`, `docs/output.md`, `site/outputs/` (zarr and preprocessing pages)

- [ ] Publish the run folder to `preprocessing/he_registration/{sample}/` (no `valis/`), not the OME-TIFF (it is in the
  store; avoids a second `{element}.ome.tif` beside the store's source).
- [ ] Describe the element, the attributes and the run folder; commit `docs: H&E registration outputs`.

### Task 7: QC report section

**Files:** `bin/qc_report.py` (`load_he_registration`, `he_registration_section`, beside `load_registration` /
`registration_section` at :880, :980), `modules/local/qc_report/main.nf` (`--he-registration`),
`subworkflows/local/qc/main.nf` (join by `meta.id`, `[]` when absent)
Test: `tests/unit/qc/test_he_registration_report.py` (pattern of `test_registration_report.py`)

- [ ] **Step 1:** failing tests: a summary with rigid, non-rigid and micro rows renders a table per stage labelled
  "automatic landmarks: agreement, not accuracy"; beyond-rigid p99 above 100 µm shows the warning; a missing folder
  renders nothing.
- [ ] **Step 2:** implement; the overview image linked from `preprocessing/he_registration/{sample}/qc/`.
- [ ] **Step 3:** run checks; commit `qc_report: H&E registration section`.

### Task 8: docs, changelog, containers, metro map

**Files:** `README.md`, `docs/usage.md`, `site/inputs/` (samplesheet, parameters), `CHANGELOG.md`, `CITATIONS.md`,
`containers.tsv`, `docs/usage.md#staging-images-into-the-shared-cache`, `docs/pipeline_paths.mmd`, `ROADMAP.md`,
`docs/decisions.md`

- [ ] README: replace "H&E is planned and not supported" with what this supports (same-section H&E registered onto
  the IF) and what it does not (H&E-only input, Longer term 5).
- [ ] CITATIONS: VALIS (Gatenbee et al. 2023, Nature Communications); verify the DOI from the paper.
- [ ] Staging: the `singularity pull` line for the new image.
- [ ] Metro map: render with the command in CONTRIBUTING; the user looks at it.
- [ ] ROADMAP: tick the track; decisions.md: drop "(planned)" from the H&E registration entries.
- [ ] Commit `docs: H&E registration`.

### Task 9: full verification

- [ ] `prek`, `uv run --frozen --group dev pytest tests/unit`, `nf-test test --tag stub,validation`,
  `nf-core pipelines lint`, `tools/clone_check.sh`.
- [ ] Propose (the user submits) exemplar-001 and exemplar-002 with `use_he_registration` false: cell counts within
  ±2% of the baselines, store element lists unchanged.
- [ ] Propose the mDVP15 run: `/fast/AG_Coscia/Levente/valis_test_mdvp15/samplesheet.csv` with an `he_image` column
  (`/ceph/coruscant/projects/RD_Coscia/Sonja/mDVP15/HE/251107_SF_mDVP15_frame_HE.czi`; scene 1 is the tissue: needs
  the scene support of the spec's "later" list, or a one-scene OME-TIFF made beforehand) and its `parameters.yml` plus
  `use_he_registration: true`.
- [ ] Check: `mDVP15.zarr` has `mDVP15_he` with the store image's shape; `preprocessing/he_registration/mDVP15/qc/`
  agrees with `registrations/mdvp15_if_to_he_v2/qc/` (fine landmarks median within 0.5 µm of about 2.5 µm, beyond-rigid
  p99 about 47 µm); the QC section renders; `-resume` after killing segmentation reuses `REGISTER_HE`.
