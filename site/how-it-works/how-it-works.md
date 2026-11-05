# How it works

The pipeline has two halves, taken from two existing projects:

- **Preprocessing**, from nf-core/mcmicro: illumination correction, stitching and registration,
  then optional TMA dearray and background subtraction.
- **Downstream**, from nf-core/sopa: the image becomes a SpatialData object on Zarr, is segmented
  tile by tile, and the cells are quantified and checked. Tiling makes segmentation independent
  of image size.

They meet at one OME-TIFF per sample, or per TMA core: the output of the last preprocessing step
that ran. When segmentation looks wrong, inspect Ashlar's stitched mosaic under
`preprocessing/registration/` first.

% source: docs/decisions.md#architecture
% source: subworkflows/local/preprocess_images/main.nf:139-142
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
