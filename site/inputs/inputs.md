# Inputs

A run needs up to three small text files next to your images:

| File         | What it says                                                       | Needed                              |
| ------------ | ------------------------------------------------------------------ | ----------------------------------- |
| Samplesheet  | Where the images are: one row per cycle, or per stitched image.    | Always                              |
| Marker sheet | What each channel is: its name, and whether it is a nuclear stain. | Raw cycles; not pre-stitched images |
| `params.yml` | What to run: segmentation method, patch size, optional steps.      | Always, in practice                 |

% source: docs/usage.md#inputs
% source: assets/schema_input_cycle.json
% source: assets/schema_input.json

Which samplesheet you write depends on where your images start:

| Your images are               | Samplesheet                                                                    | Marker sheet | Example                                           |
| ----------------------------- | ------------------------------------------------------------------------------ | ------------ | ------------------------------------------------- |
| Raw tiles, one file per cycle | [Cycle sheet](samplesheet.md#cycle-sheet), one row per cycle                   | Yes          | [Exemplar-001](../tutorials/exemplar-001.md)      |
| Already stitched elsewhere    | [Stitched-image sheet](samplesheet.md#stitched-image-sheet), one row per image | No           | [Pre-stitched image](../tutorials/prestitched.md) |

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:124-161

All three files are plain text. Write the sheets in a spreadsheet and save as CSV, and the
parameters in any text editor.

- [Samplesheet](samplesheet.md): the columns, path rules, and reusing illumination profiles.
- [Marker sheet](markers.md): channel roles, compartments, and the columns optional steps need.
- [Parameters](parameters.md): the ones most runs change, by topic.
- [All parameters](parameters-full.md): every parameter with its type and default.

The run checks the sheets and parameters when it starts, and stops with a message naming the
sample, the sheet and the column when something is wrong.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:143-162
