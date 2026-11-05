# How it works

The pipeline has two halves, taken from two existing projects. They meet at one file.

1. **Preprocessing**, from nf-core/mcmicro: illumination correction, stitching and
   registration, then optional TMA dearray and background subtraction. The result is one
   stitched OME-TIFF per sample, or per TMA core.
2. **The handoff**: that OME-TIFF is the boundary between the halves. Ashlar's stitched mosaic
   is the first file to inspect when segmentation looks wrong.
3. **Downstream**, from nf-core/sopa: the image becomes a SpatialData object on Zarr, is
   segmented tile by tile, and the cells are quantified and checked. Tiling makes segmentation
   independent of image size.

% source: docs/decisions.md#architecture
% source: README.md#what-this-is
% source: docs/output.md#preprocessing

Each page explains one step: the idea behind the method, why the pipeline uses it, what the
pipeline does with it, and what to watch out for.

Preprocessing:

- [Illumination correction: BaSiCPy](basicpy.md)
- [Stitching and registration: Ashlar](ashlar.md)
- [TMA dearray: Coreograph](coreograph.md)
- [Background subtraction: backsub](backsub.md)

Downstream:

- SpatialData
- Tiling
- Cellpose
- InstanSeg
- Channel projection
- Linking nuclei and cells
- Quantification
- QC report

Across both:

- Caveats by modality
