# Docs site restructure

From the user's review notes of 2026-11-06. Audience: bench scientists first; programmers have
GitHub. Plain language, no software jargon on user pages.

## New layout

```
site/
  index.md                      intro, animated metro map with readable station names, cards
  getting-started/
    introduction.md             what it is, who for, scope; mIF now, H&E soon
    background.md               experimental background; caveats by modality move here
    step-by-step.md             5–10 min guide for non-programmers; ends with resume/debug, results in Python
    usage.md                    the thorough usage guide (cluster, profiles, sizes, resume, GPU)
  inputs/
    inputs.md                   short summary
    samplesheet.md              + illumination profile reuse (dfp, ffp)
    markers.md                  marker sheet in detail
    parameters.md               simple guide by topic; segmentation: many markers, patch width, GPU, empty glass
    parameters-full.md          every parameter; type and default on one line
  outputs/
    outputs.md                  summary tree, what changes it
    preprocessing.md, qc.md     file by file
    reports.md                  plots and reports and what they mean; viewers; common failures
    zarr.md                     the store; why Zarr, pitfalls, current spec
  tutorials/                    exemplar-001, exemplar-002 TMA, WSI backsub, multiple segmentations,
                                stitching only, pre-stitched
  modules/                      one page per step: what it does, parameters, how it works,
                                similar tools and why this one, read more. No caveats, no summary page.
  mdc.md, reference/{usage,output}.md, changelog.md, citations.md
```

Removed: `how-to/` (folded into the pages above; offline containers dropped as maintainer-only),
`how-it-works/how-it-works.md`, `reference/parameters.md`, `reference/samplesheet.md`, stub runs
on user pages.

## Rules

- Sheets display as tables, with the CSV in a dropdown for copying.
- A module named in a tutorial links to its module page.
- Generator: parameters compact, hidden parameters outside the QC group's TOC; exemplar marker
  sheets rendered as tables from `tests/exemplar_data/`.
- Tutorials 1, 2, 4 use the exemplar data and mirror `conf/test_exemplar00*.config` where they can.
