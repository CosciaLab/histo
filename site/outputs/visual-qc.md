# Visual QC

A run that finishes is not a run that worked: nothing fails on bad QC. Look at the outputs in
this order, cheapest first.

% source: site/how-it-works/qc-report.md#caveats
% source: docs/output.md#qc-report

## 1. The QC report

Open `qc/{sample}_{m}_qc_report.html` in a browser. It is self-contained, so it opens offline.
On a TMA, start with `qc/{slide}_{m}_slide_report.html`, which names the cores that failed a
check. With `preprocessing_only` there is no report; check stitching in
`preprocessing/registration/{sample}_ashlar_qc/{sample}_ashlar_report.pdf`.

What each section shows: [QC report](../how-it-works/qc-report.md).

% source: docs/output.md#qc-report
% source: docs/output.md:115-116

:::{note} Figure pending
The top of a QC report (cell count, integrity checks, channel table), from
`qc/{sample}_cellpose_qc_report.html` of an exemplar-001 run.
:::

## 2. The stitched OME-TIFF

`preprocessing/registration/{sample}.ome.tif` is Ashlar's stitched image, and the file to
inspect first when segmentation looks wrong. With `use_backsub` or `use_tma_dearray`, the store is
built from the later image under `background_subtraction/` or `dearray/`. Ashlar writes no marker
names, so channels are unnamed here; names are added only in the store. The pixel size is in this
file.

- [QuPath](https://qupath.github.io) opens it; QuPath recommends OME-TIFF.
- [napari](https://napari.org), with a reader plugin for OME-TIFF.

% source: docs/output.md#preprocessing
% source: subworkflows/local/preprocess_images/main.nf:106-130
% source: docs/decisions.md#channel-names
% source: docs/decisions.md#pixel-size
% source: https://qupath.readthedocs.io/en/stable/docs/intro/formats.html

:::{note} Figure pending
The stitched exemplar-001 OME-TIFF in QuPath, nuclear channel and one marker.
:::

## 3. The SpatialData store

Open `{sample}.zarr` with [napari-spatialdata](https://spatialdata.scverse.org/projects/napari/en/latest/)
(`pip install "napari-spatialdata[all]"`) to see the cell outlines over the image:

```python
import spatialdata as sd
from napari_spatialdata import Interactive

sdata = sd.read_zarr("results/sample.zarr")
Interactive(sdata).run()
```

Add the image and `{m}_cells` from the plugin's element list. With `keep_projection`, the store
also holds `<image>_projected`, what Cellpose segmented, to view with the cell outlines.

% source: https://spatialdata.scverse.org/projects/napari/en/stable/notebooks/spatialdata.html
% source: https://spatialdata.scverse.org/projects/napari/en/stable/generated/napari_spatialdata.Interactive.html
% source: docs/output.md#spatialdata-directory
% source: docs/usage.md#two-channel-segmentation-use_projection

:::{note} Figure pending
napari-spatialdata with `cellpose_cells` over the image of an exemplar-001 store.
:::

:::{note} Odon
Odon, a Rust-based OME-Zarr viewer, will be documented here.
:::

## Common failures

For stitching and registration, use the table in
[When stitching or registration looks wrong](../reference/usage.md#when-stitching-or-registration-looks-wrong).

| What you see                                         | Likely cause                                                                                                                              | Where to look                                                                                                       |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Cells tile the whole tissue, ignoring membranes      | Cellpose thresholds unset, so sopa's apply; see [Two-channel segmentation](../reference/usage.md#two-channel-segmentation-use-projection) | Report "Segmentation overlay"; `qc/{sample}_projection.png`                                                         |
| Cellpose misses whole groups of cells                | One bright marker dominates the projected cell channel                                                                                    | `dominant` in `qc/{sample}_projection.json`                                                                         |
| A TMA core is missing, or two cores are one          | Wrong Coreograph downsample factor                                                                                                        | `preprocessing/dearray/{slide}_tma_map.tif`; `dearray/sweep/{slide}_sweep_overlays.png`                             |
| An empty patch inside tissue                         | Segmentation failed in that patch                                                                                                         | Report "Cells per patch"                                                                                            |
| Many tiny cells                                      | No area filter at segmentation: `min_area_pixels2` unset is 0                                                                             | Report "Integrity checks" and "Cell area distribution"                                                              |
| Last cycle's nuclear stain weaker than the first     | Cells lost between cycles, or photobleaching                                                                                              | Report "Nuclear stain across cycles"                                                                                |
| Marker columns named `Channel:0:0`, `Channel:0:1`, … | Pre-stitched input whose OME-TIFF has no channel names                                                                                    | Report "Channels"; `var['marker']` of `tables/{m}_table`                                                            |
| NaN in `cytoplasm_area` or the `cytoplasm` layer     | The cell has no linked nucleus: NaN means not measured                                                                                    | Report "Nuclei per cell"                                                                                            |
| Clusters change between runs                         | Leiden clusters were not reproducible on our test slide                                                                                   | Report "Cell clusters by marker intensity"                                                                          |
| The store does not match the parameters              | `-resume` back to earlier parameters reuses in-place writes                                                                               | `uns['segmentation']` of `tables/{m}_table`; [-resume and the store](../reference/usage.md#id-resume-and-the-store) |

% source, row by row:
% thresholds: docs/usage.md#two-channel-segmentation-use_projection, site/how-it-works/cellpose.md#caveats, bin/qc_report.py:1238
% dominant: docs/usage.md#two-channel-segmentation-use_projection, docs/output.md:250-255
% TMA core: site/how-it-works/coreograph.md#caveats, docs/output.md:97-107
% empty patch: site/how-it-works/tiling.md#caveats, bin/qc_report.py:1740-1744
% tiny cells: ROADMAP.md#known-limitations, bin/qc_report.py:1658-1667,1799, docs/output.md:227-228
% later cycles: site/how-it-works/modalities.md#cyclic-mif, bin/qc_report.py:765
% Channel:0:0: docs/decisions.md#channel-names, docs/output.md:50-52, bin/qc_report.py:650-660,738
% NaN: docs/output.md:168-176, bin/qc_report.py:852
% clusters: ROADMAP.md#findings, bin/qc_report.py:1482-1487,1573
% -resume: docs/usage.md#-resume-and-the-store, docs/output.md:163-164
