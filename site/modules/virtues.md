# VirTues: embeddings per cell and per tissue square

## What it does

VirTues is a foundation model for multiplex protein images. It gives each cell a list of 512
numbers that summarise the cell and its surroundings, across all your markers. It does the same
for each 128 µm square of tissue, and once more for the whole core or image. You can cluster these
numbers, compare cells across patients, or give them to a classifier. They have no meaning one by one.

% source: https://arxiv.org/abs/2501.06039
% source: modules/local/virtues/main.nf

## Parameters

- [`use_virtues`](../inputs/parameters-full.md#use_virtues): turns VirTues on.
- [`use_gpu`](../inputs/parameters-full.md#use_gpu), required: the model has no CPU version.
- [`use_preprocessing`](../inputs/parameters-full.md#use_preprocessing), required: the marker sheet
  gives the UniProt IDs, and a stitched image has no sheet.
- [`use_tissue_segmentation`](../inputs/parameters-full.md#use_tissue_segmentation), required:
  intensities are scaled over tissue only.
- [`segment_cells`](../inputs/parameters-full.md#segment_cells), required: cells are embedded, not nuclei.
- [`pixel_size`](../inputs/parameters-full.md#pixel_size), required: your image's pixel size in µm.
  The model works at 1 µm per pixel.
- `virtues_stats`, advanced (listed under hidden parameters in the [full list](../inputs/parameters-full.md)): a statistics file from an
  earlier run, used for every slide instead of computing new ones.

The pipeline stops at startup if one of these is missing.

% source: nextflow_schema.json
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf

## The marker sheet

The model needs to know which protein each channel shows. Add a `uniprot_id` column to the
[marker sheet](../inputs/markers.md) and fill it for each marker to embed:

| channel_number | cycle_number | marker_name | channel_role | channel_compartment | uniprot_id |
| -------------- | ------------ | ----------- | ------------ | ------------------- | ---------- |
| 1              | 1            | DNA_6       | dna          | nuclear             |            |
| 2              | 1            | ELANE       | marker       | cytoplasm           | P08246     |
| 3              | 2            | DNA_7       | dna          | nuclear             |            |
| 4              | 2            | CD11B       | marker       | membrane            | P11215     |

:::{dropdown} As CSV, to copy

```csv
channel_number,cycle_number,marker_name,channel_role,channel_compartment,uniprot_id
1,1,DNA_6,dna,nuclear,
2,1,ELANE,marker,cytoplasm,P08246
3,2,DNA_7,dna,nuclear,
4,2,CD11B,marker,membrane,P11215
```

:::

- A channel is embedded if its row has a `uniprot_id`, and only then. Leave it empty to skip a channel.
- Nuclear stains are never embedded. A `dna` row with an ID stops the run.
- Each ID may appear once. Use the human UniProt accession, e.g. `P08246`; an isoform ends in
  `-2`, `-3` and so on. An ID not in the pipeline's copy of human Swiss-Prot stops the task and is named.

% source: docs/usage.md#virtues
% source: assets/schema_marker.json

## How it works

Intensities are first scaled per marker, with numbers taken over the tissue pixels of the whole
slide: the 0.99 quantile caps each channel, then the log, then the mean and spread. On a tissue
microarray every core of a slide shares them, so cells stay comparable across cores. The numbers
are saved as `{slide}_virtues_stats.json` in `learned_features/`.

The image is then resampled to 1 µm per pixel and cut into 128 µm crops. The model embeds each
crop in patches of 8 µm, and a cell's numbers are the average over the patches it covers. Large
images are processed in [tiles](tiling.md) so memory does not grow with image area; the cell results
add about 2 GB per million cells for each segmentation method. Each cell gets
the same crops as a run on the whole image; a test encoder confirms this exactly, and the real GPU model is still being checked on the cluster.

Each square is the average of its patches, and the whole core or image is the average of its
squares. A square is kept if at least 30% of it is tissue.

The scaling differs from the model's training, which used statistics over whole datasets. Use
`virtues_stats` with one file for every slide to scale a cohort alike.

% source: docs/decisions.md#learned-features
% source: bin/virtues_cells.py
% source: bin/virtues_stats.py

**Inputs and outputs.**

| In                                    | Out                                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------------------ |
| The full image, only the marked panel | A table `{method}_virtues` per method: one row per cell, 512 columns.                |
| The cells of each segmentation method | `virtues_niches` squares and their table `virtues_niches_table`.                     |
| The tissue outline                    | `virtues_tissue`: one row for the whole core or image.                               |
| `pixel_size`                          | `{slide}_virtues_stats.json` and a settings file per sample, in `learned_features/`. |

A cell with no pixel at 1 µm per pixel gets an empty row (NaN). A slide with no square that is 30%
tissue has an empty `virtues_tissue` row. So does a core where tissue segmentation finds no tissue;
its cells are still embedded. See [The SpatialData store](../outputs/zarr.md).

% source: docs/output.md#virtues-embeddings

## Open points

- The model's agreement with the authors' own code, and between two runs, is being measured on the
  cluster. Whether the numbers help on your data has not yet been tested.
- The weights (`sp32`) are licensed CC BY-NC 4.0: academic and non-commercial use only.

% source: docs/decisions.md#learned-features

## Read more

- VirTues: [Nature paper](https://doi.org/10.1038/s41586-026-10884-y) and
  [preprint](https://arxiv.org/abs/2501.06039). The model code is MIT.
- [VirTues on GitHub](https://github.com/bunnelab/virtues).
- ESM-2, which turns each protein into a vector: [@doi:10.1126/science.ade2574].

Version used:

```{include} ../_generated/modules/virtues.md

```
