# Figures

Maintainer checklist, not part of the site. One line per figure or figure slot.

Paper figures are reused only under CC BY 4.0, checked on the publisher page.

## Paper figures

- modules/basicpy: `images/modules/basic-fig1.jpg` — Fig. 1, doi:10.1038/ncomms14836, CC BY 4.0 (nature.com article page, "Rights and permissions")
- modules/ashlar: `images/modules/ashlar-fig2.jpg` — Fig. 2, doi:10.1093/bioinformatics/btac544, CC BY 4.0 (academic.oup.com article page)
- modules/spatialdata: `images/modules/spatialdata-fig1.png` — Fig. 1, doi:10.1038/s41592-024-02212-x, CC BY 4.0 (nature.com article page, "Rights and permissions")
- modules/instanseg: `images/modules/instanseg-channelnet-fig1.jpg` — Fig. 1, doi:10.1101/2024.09.04.611150, CC BY 4.0 (biorxiv.org article page licence line)

## Own diagrams

- modules/tiling: `images/modules/tiling.svg` — two overlapping patches and a resolved cell, drawn for this site
- modules/linking: `images/modules/linking.svg` — a linked and an unlinked nucleus, drawn for this site

## Slots

- modules/coreograph: detected cores at downsample factors 3 to 7, side by side — `preprocessing/dearray/sweep/{slide}_sweep_overlays.png` from an exemplar TMA run
- modules/backsub: one marker channel before and after subtraction, with its autofluorescence channel — WSI background-subtracted exemplar run
- modules/cellpose: Cellpose outlines on one full-resolution crop — "Segmentation overlay" of an exemplar-001 QC report (Cellpose-SAM preprint is CC BY-NC, Cellpose 2021 is not open access)
- modules/projection: the projection preview, nuclear magenta and cell green — `qc/{sample}_projection.png` of an exemplar-001 run with `use_projection`
- modules/quantification: one cell with whole-cell, nucleus and cytoplasm outlines over a marker, and its table row — exemplar-001 run with both targets
- modules/qc-report: top of a QC report (cell count, integrity checks, channel table) — `qc/{sample}_cellpose_qc_report.html` of exemplar-001
- outputs/reports: the stitched OME-TIFF in QuPath, nuclear channel and one marker — `preprocessing/registration/{sample}.ome.tif` of exemplar-001
- outputs/reports: napari-spatialdata with `cellpose_cells` over the image — `{sample}.zarr` of exemplar-001
