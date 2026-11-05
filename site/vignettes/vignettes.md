# Vignettes

Complete runs for common cases: inputs, parameters, command, outputs and what to check.

| Use case                                  | Vignette                             | Route                                 |
| ----------------------------------------- | ------------------------------------ | ------------------------------------- |
| Cyclic mIF slide, two methods compared    | [mIF slide](mif-slide.md)            | Cellpose + InstanSeg, cells + nuclei  |
| Whole slide with autofluorescence removed | [WSI with backsub](wsi-backsub.md)   | backsub, Cellpose, cells              |
| Tissue microarray                         | [TMA](tma.md)                        | Coreograph, InstanSeg, cells + nuclei |
| Image already stitched elsewhere          | [Pre-stitched image](prestitched.md) | `use_preprocessing: false`, Cellpose  |
| Stitched images only                      | [Stitching only](stitching-only.md)  | `preprocessing_only: true`            |

% source: docs/output.md#what-runs

Paths are examples; use absolute paths. Before submitting, a `-stub` run checks paths and
parameters in seconds; see [Running on the cluster](../reference/usage.md#running-on-the-cluster).

% source: docs/usage.md:108
% source: docs/usage.md:301-306
