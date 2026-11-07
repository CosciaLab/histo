# Tutorials

Complete runs, from the input sheets to what to check in the results. Tutorials 1, 2 and 4 use
public example data, so you can follow them before using your own images.

| Tutorial                                                     | Use case                                                    | Data                  |
| ------------------------------------------------------------ | ----------------------------------------------------------- | --------------------- |
| [1: Your first run](exemplar-001.md)                         | A small tissue region, one segmentation, no optional steps  | exemplar-001          |
| [2: Tissue microarray](tma.md)                               | A TMA cut into cores, each segmented, then merged per slide | exemplar-002, 4 cores |
| [3: Whole slide with background subtraction](wsi-backsub.md) | Autofluorescence removed from the markers before segmenting | your own              |
| [4: Multiple segmentations](multiple-segmentations.md)       | Cellpose and InstanSeg, cells and nuclei, compared          | exemplar-001          |
| [5: Stitching only](stitching-only.md)                       | Corrected, stitched and registered images, nothing after    | your own              |
| [6: Pre-stitched image](prestitched.md)                      | Images stitched elsewhere: segmentation, quantification, QC | your own              |

New to the pipeline? Read the [step-by-step guide](../getting-started/step-by-step.md) first,
then do Tutorial 1. Use absolute paths in every sheet and parameter file.

% source: conf/test_exemplar001.config
% source: conf/test_exemplar002.config
% source: docs/output.md#what-runs
% source: docs/usage.md:108
