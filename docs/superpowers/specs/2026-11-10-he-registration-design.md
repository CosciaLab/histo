# H&E registration with VALIS: a same-section H&E in the sample's store

New ROADMAP track (Separate track: H&E registration). Not breaking: off by default, and a run without it is unchanged.
The image comes from `valis_pipeline` (`leventetn/valis_registration_pipeline`), specified in its
`docs/superpowers/specs/2026-11-10-histo-container-design.md`.

## Goal

When a sample has an H&E of the same section, scanned after the IF, the run registers it onto the stitched IF right
after Ashlar and adds it to the sample's store as `{sample}_he`, on the IF pixel grid, so cells, shapes and H&E share
one frame. The registration's maps and QC are published, and the QC report gets a section on it.

Success: stub and validation nf-tests pass with an `he_image` column; exemplar-001 and exemplar-002 without it give
the same cell counts (±2%) and outputs as before; mDVP15 (IF tiles and H&E CZI on the cluster) gives a store with
`{sample}_he`, and its maps and QC agree with the standalone `valis_pipeline` run of the same pair
(`registrations/mdvp15_if_to_he_v2`: fine landmarks median about 2.5 µm, beyond-rigid p99 about 47 µm).

Out of scope for this release: TMA slides, H&E segmentation, serial (not same-section) H&E.

## Findings that shape the design

- **VALIS does not stitch.** It registers whole images: Ashlar's mosaic and the scanner's pyramid. Rigid and non-rigid
  run on downsampled whole images; micro registration cuts both into 1024 px tiles with a 100 px overlap and joins the
  displacement fields with libvips `merge` at fixed positions, blended over the overlap (no offset search, so a jump
  between tiles is feathered, not resolved). One point map comes out; the H&E is pulled through it in tiles that share
  that map, so the output has no seams.
- **Ashlar writes no channel names** (decisions.md, Channel names). The registration channel is chosen by index: the
  first `dna` channel, Ashlar's reference and the best registered (`dearrayChannel`, already used for Coreograph).
- **Backsub keeps Ashlar's pixel grid** and only drops channels, so a map made on Ashlar's output holds for the
  `{sample}_backsub` element too. Registering on Ashlar's output keeps the H&E off the critical path of backsub.
- **Three steps assume one image in the store**: `SET_CHANNEL_NAMES` (`bin/set_channel_names.py:84-89`),
  `TISSUE_SEGMENTATION` and `PROJECT_CHANNELS` when `cell_segmentation_image` is unset. sopa's tissue `auto` mode reads
  a 3-channel image as H&E.
- **Nothing writes after `WRITE_SEGMENTATIONS`**, so QC and the merge read the store concurrently
  (`workflows/histo.nf:110-112`). A new writer must come before them.
- **The chosen VALIS setting** (valis_pipeline decisions: rigid 1000 px, non-rigid 4000 px, DeepFlow, micro at the
  coarser image's pixel) took 2.5 h and 28 GB on mDVP15 at 0.5 µm, and 174 min and 45 GB on a whole Orion slide.
- **H&E against fluorescence** needs the H&E registered as hematoxylin against its measured glass brightness; VALIS'
  default (glass 240) failed on mDVP15. `valis_pipeline` does this already; nothing to add here.
- **Automatic landmarks measure agreement, not accuracy.** Manual landmarks are the only accuracy measure; the QC
  section must say which it shows.

## Inputs

- `he_image`: new optional last column in `assets/schema_input_cycle.json` and `assets/schema_input.json` (last, so
  the positional indexes in `utils_nfcore_histo_pipeline/main.nf` (117, 229, 266, 278) do not shift). Path to a
  brightfield RGB `.svs`, `.czi` or `.ome.tif`. On cycle rows it must be equal on every row of a sample, checked like
  `marker_sheet` (`validateMarkerSheetColumn`), and emitted as `[[id: sample], file]`.
- A CZI with several scenes or a slide with several samples is out of scope here (valis_pipeline's `scene` and
  `polygon`); a later column can carry them.

## Parameters

- `use_he_registration` (boolean, default `false`). **Requires:** `he_image` for every sample that should get one;
  samples without it run as today, with a log line.
- `he_placement` (`search` default, `none`): coarse placement. `search` (nuclei correlation at 90 angles, mirrored or
  not) is what mDVP15 used; `none` is VALIS' own features, untested for H&E against IF.
- `he_placement_check` (`stop` default, `skip`): with `stop`, an ambiguous placement (gap < 0.1) fails the task naming
  `qc/placement.jpg`; with `skip` it runs anyway.
- `he_micro_um` (`native` default, or a number in µm): micro-registration field pixel.
- Fixed, not params: rigid 1000 px, non-rigid 4000 px, DeepFlow, `same_section: true`, `inverse: invert`.
- `validateParams`: `use_he_registration` with `use_tma_dearray` fails ("TMA slides are not supported yet");
  `use_he_registration` with `preprocessing_only` fails (no store to add to).

## Processes

**`REGISTER_HE`** (`modules/local/register_he`, image `docker.io/leventetn/valis_pipeline:<version>`).
- Input: `[meta, ifimage, heimage]`, `val(channel_index)`.
- Writes `config.yml` in the work directory (`outdir: .`, `name: {sample}`, reference `{path: ifimage,
  channel_index}`, moving `{path: heimage}`, the params above, `spatialdata_mode: none`) and runs
  `python /opt/valis_pipeline/scripts/run.py config.yml`.
- Outputs: `[meta, {sample}/]` (config, `placement.json`, `registration.json`, `maps/`, `qc/`), `[meta,
  {sample}_he.ome.tif]` (the H&E on the IF grid, pyramid), `qc/summary.csv` for the report, versions (valis-wsi and
  the valis_pipeline commit from `registration.json`). The VALIS working folder is deleted before the task ends.
- Inputs come from `ASHLAR.out.tif` joined with `he_image`, or the supplied image when `use_preprocessing: false`.
- Resources from `conf/sizes.config`; first values from the mDVP15 runs (8 CPUs, 64 GB, 12 h), `size_huge` 256 GB.
- Stub: writes the folder layout, an empty `qc/summary.csv` with the header, and a 1 × 1 RGB OME-TIFF.

**`ADD_REGISTERED_IMAGE`** (`modules/local/add_registered_image`, `bin/add_registered_image.py`, sopa image).
- Input: `[meta, sdata, he_tif, run_dir]`. The single writer of the H&E: adds image element `{sample}_he` (c = r, g,
  b; uint8; `Identity` to `global`; pyramid as the store's image), checks its height and width equal the store image's,
  refuses an existing name, and writes `he_registration` into the store group attributes: valis_pipeline commit, map
  stage, `um_per_px` of both images, placement gap, and the paths of the published run.
- Runs after `SEGMENTATION`, before `QC`, `COMPARE_SEGMENTATIONS` and `PUBLISH_SPATIALDATA`. Samples without
  `he_image` pass through unchanged.
- `cell_segmentation_image` is not changed.

## Outputs

- `preprocessing/he_registration/{sample}/`: the run folder, as `valis_pipeline` writes it.
- `{sample}.zarr/images/{sample}_he/`: the H&E on the IF pixel grid.
- QC report, new section "H&E registration" after "Stitching and registration", from `qc/summary.csv` and
  `placement.json`, in the pattern of `load_registration` / `registration_section` (`bin/qc_report.py:880, 980`):
  placement gap and angle, automatic landmarks per stage (labelled "agreement, not accuracy"), beyond-rigid p99 with
  the same-section warning (1% of the tissue more than 100 µm), folded tissue, round trip, and `overview_micro.jpg`.

## Later, kept possible

- **H&E segmentation.** An InstanSeg `brightfield_nuclei` spec naming `{sample}_he` as its image; specs already pass
  an explicit `image_key` (decisions.md, Segmentation). v1 keeps the H&E on the IF grid with Identity so patches,
  shapes and ids share one frame. Enabling it moves `ADD_REGISTERED_IMAGE` before `MAKE_IMAGE_PATCHES` and makes
  `SET_CHANNEL_NAMES`, `TISSUE_SEGMENTATION` and `PROJECT_CHANNELS` name their image. Check first: the IF pixel may be
  coarser than InstanSeg's 0.5 µm training scale (exemplar-001 0.65 µm), the weights must be baked into the image, and
  on the PANAMA post-Xenium H&E it found about a third as many nuclei as Xenium's DAPI segmentation.
- **TMA.** Register the whole slide before Coreograph, then crop the H&E per core. Coreograph records no core boxes
  and merged cores sit at identity in their own frames; mapping cores back to the slide comes first.
- **Finer than the IF pixel.** `valis_pipeline`'s `output_um` gives N × N H&E pixels per IF pixel with a `Scale`
  transformation; deferred, as it puts a non-identity element in a pixel-only store (decisions.md, Pixel size).
