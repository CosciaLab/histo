# 3.1: documentation website

Replaces ROADMAP 3.1. Not an nf-core site; inspired by MCMICRO, sopa and quantmsdiann.

## Goal

A public site at `https://coscialab.github.io/histo/` for colleagues who know little Nextflow:
how to run the pipeline on their data, what every parameter does and conflicts with, what comes
out and how to check it by eye, and how each step works and why.

Success: the site builds in CI with no broken internal links; every page is drafted; every
factual claim traces to a file, a code line or a DOI; a reviewer agent that has not seen the
drafting finds no claim contradicting the code; the user has looked at screenshots of every
page.

## Findings that shape the design

- **Material for MkDocs (sopa's stack) reaches end of support on 2026-11-05**; its successor
  Zensical is young. MCMICRO uses Jekyll; quantms uses Sphinx.
- **MyST (`mystmd`) does not need notebooks.** It gives numbered figures, DOI citations,
  admonitions, tabs, cards and an `include` directive. It needs Node, pinned via npm.
- **Conflict rules live in code**: `error()` and `log.warn` in
  `subworkflows/local/utils_nfcore_histo_pipeline/main.nf` and the segmentation and preprocessing
  subworkflows. Only 14 of ~70 schema parameters have a `help_text`.
- **`docs/usage.md` and `docs/output.md` are nf-core files** and stay the source for what they
  cover. They contain relative links (`output.md#from-1x`, `../README.md`) that may resolve
  differently when included.
- **The dropbox repo (`josenimo/histo-dropbox`) is private** and its guide holds internal paths.
- **The repo is public; Pages is off.**

## Layout

```
site/
  myst.yml                 nav, theme, GitHub link, BASE_URL=/histo
  package.json             pins mystmd
  index.md                 what it is, metro map, where to start
  getting-started.md       install, profiles, first run; Nextflow in one paragraph + links
  vignettes/               5 end-to-end runs
  how-to/                  task recipes
  reference/
    usage.md               {include} ../../docs/usage.md
    output.md              {include} ../../docs/output.md
    parameters.md          hand-written conflicts section + generated reference
    samplesheet.md         generated
  outputs/                 what to expect, what changes it, visual QC
  how-it-works/            one page per step, plus caveats by modality
  mdc.md                   At the MDC
  changelog.md             {include} ../CHANGELOG.md
  citations.md             {include} ../CITATIONS.md
  images/
  _generated/              gitignored, written by tools/site_reference.py
tools/site_reference.py
.github/workflows/docs.yml
```

`docs/` is not changed except where an included file's links must work in both places.

## Content

**Getting started.** Requirements, profiles, the two input sheets, first run. Nextflow gets one
paragraph and links to its docs.

**Vignettes**, each with use case, samplesheet, marker sheet, `params.yml`, command, outputs,
what to check:

1. Cyclic mIF slide, Cellpose + InstanSeg, cells + nuclei.
2. Whole-slide image with background subtraction.
3. TMA, dearrayed and merged per slide.
4. Pre-stitched image (`use_preprocessing: false`).
5. Stitching only (`preprocessing_only: true`).

**How-to guides**: write the input sheets; choose methods, channels and targets; use
projection; choose `patch_width_pixel`; run on GPU; skip empty tissue; supply illumination
profiles; fix stitching; resume or debug a failed run; stage containers offline; load results
in Python. Where `usage.md` covers a topic, link its section and add only what it lacks.

**Outputs.**

- What to expect: the folder tree and SpatialData layout, linking `output.md`.
- What changes it: a table of parameter → what appears, disappears or changes in `outdir` and the
  store.
- Visual QC: what to inspect and in which order and viewer: the QC report, the stitched
  OME-TIFF (QuPath, napari), the store (napari-spatialdata; Odon as a marked slot, documented
  later), and a checklist of common failures and how they look.

**How it works.** One page each: BaSiCPy, Ashlar, Coreograph, backsub, SpatialData on Zarr,
tiling and resolve, Cellpose, InstanSeg, projection, nucleus–cell linking, quantification, QC
report. Each has: the idea with a figure; why this pipeline uses it; tool, version and container
(generated); the parameters that steer it; caveats; the paper by DOI. Plus **Caveats by
modality**: cyclic mIF (tissue loss, photobleaching), TMA, WSI, pixel-size metadata, H&E not
supported. Facts come from `decisions.md`, `CHANGELOG.md`, ROADMAP known limits and the papers.

**At the MDC.** The dropbox exists and runs the pipeline for you; which params it blocks; what
`size:` means; where the full guide is (the private repo or the shared drive). No internal
paths.

**Figures.** A paper figure is reused only under CC BY, with source and licence in the caption;
otherwise a simple diagram or a link. Exemplar-001 figures and viewer screenshots need cluster
outputs: each gets a marked slot, listed in one checklist for the user.

## Generated reference

`tools/site_reference.py`, standard library only, writes Markdown to `site/_generated/`:

- **Parameters**: per schema group, per parameter: type, default, enum, description,
  `help_text`, anchor `#<name>`. Hidden parameters in a collapsed block.
- **Input sheets**: columns from `assets/schema_input_cycle.json`, `schema_input.json`,
  `schema_marker.json`.
- **Module facts**: tool, version, container per module from `main.nf` and `meta.yml`; each
  how-it-works page includes its block.

## Conflicts

Every startup check is read and written into the `help_text` of each parameter it involves, as
one line: `**Requires:** … **Conflicts:** … **Ignored unless:** …`. So `--help`, the site and
the params template show the same rule (check `tools/params_templates.py` renders `help_text`).
A pytest test asserts every parameter named in a check has a `help_text`. `parameters.md` opens
with a hand-written "Common combinations and conflicts": the `use_*` routes, method × target,
`use_projection` vs `cellpose_channels`, TMA requirements, booleans on the command line.

## Build and deploy

- Local: `uv run tools/site_reference.py`, then `cd site && npx myst start`.
- `.github/workflows/docs.yml`: generate and build on PRs and pushes to `dev` and `main`;
  deploy with `actions/deploy-pages` from `main` only, so the site matches the release.
- The user switches Pages' source to GitHub Actions in repo settings.

## Testing

- CI build fails on broken internal links and missing includes (`--strict` if the pinned
  mystmd has it). External links checked, warn only.
- pytest: the generator on a fixture schema; the `help_text` coverage test.
- Headless Chrome screenshots of every page for the user.
- A reviewer agent, given pages and code but not this conversation, checks claims against the
  code.

## Bookkeeping

README Documentation table and `docs/README.md` link the site. ROADMAP 3.1 rewritten.
CHANGELOG "Added". CONTRIBUTING gets a "Docs site" section. `.prettierignore` if prettier breaks
MyST directives. Branch `feat/docs-site`, one commit per page group.

## Risks

- **Included files' relative links.** Tested first. Fallback: rewrite those links in `docs/` to
  forms that work in both places.
- **Volume.** The whole site lands in one branch; drafted pages are expected to be pruned.
- **mystmd flags** (`--strict`, `--check-links`) are unverified for the pinned version.

## Out of scope

Odon documentation; versioned docs per release; a custom domain; per-module pages beyond the
twelve steps above.
