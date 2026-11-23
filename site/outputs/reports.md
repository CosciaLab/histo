# Plots and reports

A run that finishes is not a run that worked: nothing fails on bad QC. Look at the outputs in
this order, cheapest first: the QC report, then the stitched image, then the store.

% source: docs/output.md#qc-report
% source: bin/qc_report.py:1784-1790

## The QC report

Open `qc/{sample}_{m}_qc_report.html` in a browser; it opens offline. On a TMA, start with the
[slide report](#slide-report). With `preprocessing_only` there is no report; check stitching in
`preprocessing/registration/{sample}_ashlar_qc/{sample}_ashlar_report.pdf`.

The report gives numbers, not a verdict: it sets no thresholds. The sections, top to bottom:

% source: docs/output.md#qc-report
% source: bin/qc_report.py:1767-1812

:::{note} Figure pending
The top of an exemplar-001 QC report: cell count, integrity checks and the channel table.
:::

### Summary tiles

The number of cells segmented, then the image size and channel count, the median cell area, the
number of cells below the minimum area, and the number of patches with how many came out empty.
Compare the median area with the cells you expect: at 0.65 µm per pixel, a cell 10 µm across is
about 190 px².

% source: bin/qc_report.py:1685-1705

### Integrity checks

A list of yes/no observations:

| Check                                  | A "no" means                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------------ |
| Table and image agree on channel names | the measurements may belong to the wrong marker                                      |
| Image matches the marker sheet         | the sheet lists different names or a different number of channels than the image has |
| Every channel has a `channel_role`     | a row of the marker sheet is incomplete                                              |
| A nuclear stain is declared            | no `dna` channel; the cross-cycle check guesses from the names                       |
| No cells below 10 px²                  | some outlines are specks, not cells; set `min_area_pixels2` to drop them             |
| Every patch produced cells             | a patch found nothing; see [Cells per patch](#cells-per-patch)                       |

% source: bin/qc_report.py:1617-1680
% source: bin/qc_metrics.py:124-140

### Channels

One row per channel: a small intensity histogram, its role, the compartment it is expected in,
and the mean, median and share of zero pixels. Measured on every pixel of the full-resolution
image. All histograms share one scale, so a curve hugging the left is a dim channel.

- **Good:** each marker has a spread of intensities, with a tail of bright pixels.
- **Bad:** a marker whose histogram looks like background, or many zero pixels in a channel
  that should have signal.

"Zero pixels per channel" follows. With background subtraction it shows each channel before
and after: subtraction clips at zero, so pixels driven to zero are signal it removed. A marker
driven almost entirely to zero was subtracted away, often from a wrong `exposure` in the marker
sheet.

% source: bin/qc_report.py:650-757

### Nuclear stain across cycles

Per cell, the last cycle's nuclear stain divided by the first cycle's, on a log2 scale: 0 is no
change, −1 is half. Every cycle images the same nuclei, so a drop is the sample or the optics,
not biology.

- **Good:** a narrow peak near 0.
- **Bad:** a shoulder on the left, cells that lost their signal: tissue that detached or folded
  in a wash. A whole peak shifted left is photobleaching or a dimmer last cycle.

% source: bin/qc_report.py:760-835

### Stitching and registration

From Ashlar's own records. The tile map draws each tile at its stitched position; thick lines
placed tiles, thin lines agreed, **dashed red lines were rejected**. A cluster of red lines
inside tissue is where stitching failed. "Later cycles against cycle 1" counts the tiles of each
cycle that could not be aligned and were placed by the stage position instead, and shows the
cycle overlays: grey where cycles align, magenta and green fringes where they do not.

- **Good:** few red lines, all at the tissue edge; overlays grey.
- **Bad:** red lines or discarded tiles in the middle of tissue; coloured fringes.

What to change: [Ashlar](../modules/ashlar.md#when-stitching-looks-wrong). On a TMA this section
is in the slide report, not the cores'.

% source: bin/qc_report.py:980-1210

### Cell area distribution

A histogram of cell areas in px², up to the 99th percentile, with a table of percentiles.

- **Good:** one peak where your cells are.
- **Bad:** a second peak of tiny objects (noise segmented as cells), or a long tail of huge
  ones (cells merged together, or patches of tissue taken as one cell).

% source: bin/qc_report.py:1706-1725

### Nuclei per cell

With cells and nuclei: how many cells hold 0, 1 or more nuclei, how many nuclei belong to no
cell, and how many cells their nuclei fill completely.

- **Good:** most cells hold one nucleus.
- **Bad:** many cells with none (cells drawn where there is no nucleus) or with two or more
  (merged cells; some are dividing).

% source: bin/qc_report.py:838-860

### Cells per patch

The number of cells in each patch, laid out as the patch grid. An empty patch at the slide's edge
is background; **an empty patch in the middle of tissue is a failure**. Patches overlap, so the
counts add up to more than the total.

% source: bin/qc_report.py:1738-1750

### Segmentation overlay

With `use_qc_images`: full-resolution windows with the outlines in red over the nuclear stain,
chosen from the densest to the sparsest part of the image. Click to enlarge.

- **Good:** one outline per cell, following its edge, in packed and sparse areas alike.
- **Bad:** cells split in two, neighbours merged, outlines that ignore cell edges and tile the
  tissue, or empty areas with outlines.

% source: bin/qc_report.py:1213-1250

### Cell clusters and representative cells

With `use_qc_images`: cells grouped by their marker intensities alone (Leiden clustering), shown
as a tree across resolutions and a heatmap of each cluster's markers. Below, a few typical cells
of each cluster, in the cluster's top marker (magenta) over the nuclear stain (green).

- **Good:** clusters with distinct marker profiles whose example cells look like that profile.
- **Bad:** one big undifferentiated cluster (markers did not work), or example cells that do not
  show their cluster's marker (the cluster is an artefact).

These clusters are a summary of the staining, not cell types. They were not reproducible
between random seeds on our test slide, and the report says so when that happens.

% source: bin/qc_report.py:1421-1600
% source: docs/output.md#qc-report

## Comparison report

`qc/{sample}_comparison.html`, when both Cellpose and InstanSeg segment cells. It shows the cell
count and median area of each method, the share of each method's cells that the other found as
well (paired one-to-one when their shared area is at least half of their combined area, IoU ≥
0.5), and both outlines on the densest, median and sparsest window: Cellpose in orange,
InstanSeg in blue.

Neither method is the reference. Large differences in count or area show where to look in the
overlays; the overlays decide which method suits your tissue.

% source: bin/compare_segmentations.py:225-285

## Slide report

`qc/{slide}_{m}_slide_report.html`, on a TMA. One page for the whole slide, built from the cores'
metrics:

- **Integrity checks**, rolled up: a check passes only when every core passes, and the cores that
  failed are named.
- **Cells per core.** A core far below its neighbours lost tissue or failed segmentation; inside
  that core's own report the count has nothing to be compared with.
- **Channels across cores**: mean intensity per channel, one column per core. A stain that failed
  on one core stands out only side by side.
- **Nuclear stain across cycles**, per core.
- **Background subtraction, before and after**, per core, with `use_backsub`. A marker driven to
  zero on every core points to the marker sheet; on one core, to that core.
- **Stitching and registration**, for the slide.

Then open the reports of the cores it names.

% source: bin/merge_report.py:181-405
% source: docs/output.md#qc-report

## Viewers

### The stitched OME-TIFF

`preprocessing/registration/{sample}.ome.tif` is the stitched image, and the file to open first
when segmentation looks wrong. Its channels have no names: names are added only in the store.

- [QuPath](https://qupath.github.io) opens it; QuPath recommends OME-TIFF.
- [napari](https://napari.org), with a TIFF reader plugin.

% source: docs/output.md#preprocessing
% source: docs/decisions.md#channel-names
% source: https://qupath.readthedocs.io/en/stable/docs/intro/formats.html

:::{note} Figure pending
The stitched exemplar-001 OME-TIFF in QuPath, nuclear channel and one marker.
:::

### The store

Open `{sample}.zarr` with [napari-spatialdata](https://spatialdata.scverse.org/projects/napari/en/latest/)
(`pip install "napari-spatialdata[all]"`) to see the cell outlines over the image:

```python
import spatialdata as sd
from napari_spatialdata import Interactive

sdata = sd.read_zarr("results/sample.zarr")
Interactive(sdata).run()
```

Add the image and `{m}_cells` from the plugin's element list. With `keep_projection`, the store
also holds `<image>_projected`, what Cellpose segmented, to view under the outlines. More on the
store: [The Zarr store](zarr.md).

% source: https://spatialdata.scverse.org/projects/napari/en/stable/notebooks/spatialdata.html
% source: docs/output.md#spatialdata-directory

:::{note} Figure pending
napari-spatialdata with `cellpose_cells` over the image of an exemplar-001 store.
:::

:::{note} Odon
Odon, a Rust-based OME-Zarr viewer, will be documented here.
:::

## Common failures

For stitching and registration, see [Ashlar](../modules/ashlar.md#when-stitching-looks-wrong).

| What you see                                         | Likely cause                                                                                                    | Where to look                                                                           |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Cells tile the whole tissue, ignoring membranes      | Cellpose thresholds unset; see [Many markers with Cellpose](../inputs/parameters.md#many-markers-with-cellpose) | "Segmentation overlay"; `qc/{sample}_projection.png`                                    |
| Cellpose misses whole groups of cells                | One bright marker dominates the projected cell channel                                                          | `dominant` in `qc/{sample}_projection.json`                                             |
| A TMA core is missing, or two cores are one          | Wrong Coreograph downsample factor                                                                              | `preprocessing/dearray/{slide}_tma_map.tif`; `dearray/sweep/{slide}_sweep_overlays.png` |
| An empty patch inside tissue                         | Segmentation failed in that patch                                                                               | "Cells per patch"                                                                       |
| Many tiny cells                                      | No area filter: `min_area_pixels2` unset is 0                                                                   | "Integrity checks" and "Cell area distribution"                                         |
| Last cycle's nuclear stain weaker than the first     | Cells lost between cycles, or photobleaching                                                                    | "Nuclear stain across cycles"                                                           |
| Marker columns named `Channel:0:0`, `Channel:0:1`, … | Pre-stitched input whose OME-TIFF has no channel names                                                          | "Channels"; `var['marker']` of `tables/{m}_table`                                       |
| NaN in `cytoplasm_area` or the `cytoplasm` layer     | No linked nucleus, nuclei fill the cell, or the cell covers no pixel centre; see [NaN and 0](zarr.md#nan-and-0) | "Nuclei per cell"                                                                       |
| Clusters change between runs                         | Leiden clusters were not reproducible on our test slide                                                         | "Cell clusters by marker intensity"                                                     |
| The store does not match the parameters              | `-resume` back to earlier parameters reuses in-place writes; see [Pitfalls](zarr.md#pitfalls)                   | `uns['segmentation']` of `tables/{m}_table`                                             |

% source, row by row:
% thresholds: docs/usage.md#two-channel-segmentation-use-projection, bin/qc_report.py:1238
% dominant: docs/usage.md#two-channel-segmentation-use-projection, docs/output.md:250-255
% TMA core: docs/output.md:97-107
% empty patch: bin/qc_report.py:1740-1744
% tiny cells: ROADMAP.md#known-limitations, bin/qc_report.py:1658-1667,1799, docs/output.md:227-228
% later cycles: bin/qc_report.py:765
% Channel:0:0: docs/decisions.md#channel-names, docs/output.md:50-52, bin/qc_report.py:650-660,738
% NaN: docs/output.md:168-176, bin/qc_report.py:852
% clusters: ROADMAP.md#findings, bin/qc_report.py:1482-1487,1573
% -resume: docs/usage.md#id-resume-and-the-store, docs/output.md:163-164
