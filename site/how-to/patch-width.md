# Set `patch_width_pixel`

Goal: a patch size that lets segmentation run in parallel and fit in memory.

The rule and the table are in [Choosing
`patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel); why patches exist, in
[Tiled segmentation](../how-it-works/tiling.md).

## Steps

1. Get the stitched image size from `preprocessing/registration/{sample}.ome.tif`, for example
   from a [stitching-only](../vignettes/stitching-only.md) run:

   ```bash
   python -c "import tifffile; print(tifffile.TiffFile('slide01.ome.tif').series[0].shape)"
   ```

2. Aim for 16 to 200 patches: `patch_width_pixel = sqrt(width × height / patches)`. A
   30 000 × 20 000 px image at 70 patches gives 2928; round to 3000.
3. With InstanSeg, check the memory one patch task asks for, with the formula in
   [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel). At 3000 px,
   0.65 µm/px and 8 channels it is 39 GB. Above 64 GB the run warns and names a width that fits.
4. Leave [`patch_overlap_pixel`](../reference/parameters.md#patch_overlap_pixel) at about twice
   a cell diameter (default 100).
5. After the run, open the QC report's "Cells per patch" map. An empty patch inside tissue is a
   failure; empty patches at the slide edge are background.

% source: docs/usage.md#choosing-patch-width-pixel
% source: docs/output.md#preprocessing
% source: modules/local/utils.nf:171-189
% source: subworkflows/local/segmentation/main.nf:56-69
% source: site/how-it-works/tiling.md#caveats
% source: bin/qc_report.py:1738-1750

## Pitfalls

- **Keep the width when you compare runs.** It changes results at patch boundaries.
- **One patch means no parallelism**; thousands cost more in scheduling than in work.
- **The memory doubles on retry**, so a request near a node's limit may not fit the second time.

% source: docs/decisions.md#parameters
% source: docs/usage.md#choosing-patch-width-pixel
% source: subworkflows/local/segmentation/main.nf:56-64
% source: conf/base.config:66-67
