# Choose methods and targets

Goal: pick the segmentation methods and targets for your question, and know what each costs.

## Steps

1. Pick one or both methods:

   | You want                                   | Set                                                                                                  |
   | ------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
   | Cells from one membrane marker and DNA     | `use_cellpose: true`, `cellpose_channels: "CD45 DNA_1"`, nuclear last                                |
   | Cells from many markers, with Cellpose     | `use_cellpose: true`, `use_projection: true`; see [Segment cells on many markers](use-projection.md) |
   | Cells from every marker, no channel choice | `use_instanseg: true`, `instanseg_pixel_size` (µm per pixel); channels come from the marker sheet    |
   | A second opinion                           | Both. With both segmenting cells and `use_qc`, `qc/{sample}_comparison.html` compares them           |

2. Pick the targets. Cells are on by default.

   | You want                            | Set                                            |
   | ----------------------------------- | ---------------------------------------------- |
   | Cells                               | nothing                                        |
   | Cells, nuclei and cytoplasm, linked | `segment_nuclei: true`                         |
   | Nuclei only                         | `segment_cells: false`, `segment_nuclei: true` |

3. Count the cost: every method × target is one more pass over every patch. Two methods with two
   targets are four segmentations per patch.

% source: docs/usage.md#parameters
% source: docs/usage.md#methods-and-targets
% source: modules/local/utils.nf:57-68
% source: modules/local/utils.nf:196-201
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:642-668

What each method does: [Cellpose](../how-it-works/cellpose.md),
[InstanSeg](../how-it-works/instanseg.md), [Linking nuclei and cells](../how-it-works/linking.md).
What each choice adds to the store: [What changes the outputs](../outputs/what-changes-it.md).

## Pitfalls

- **Nuclei come from a nuclear channel.** Cellpose segments nuclei on the last of
  `cellpose_channels` (the projection's `nuclear` channel with `use_projection`); InstanSeg on
  `dna` channels, unless `instanseg_channels` is set.
- **Pre-stitched input has no marker sheet**, so InstanSeg needs `instanseg_channels`, and
  `use_projection` is not available.
- **InstanSeg's memory grows with patch area × channels**; see [Set `patch_width_pixel`](patch-width.md).

% source: docs/usage.md#methods-and-targets
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:651-654
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-676
% source: docs/usage.md#choosing-patch-width-pixel
