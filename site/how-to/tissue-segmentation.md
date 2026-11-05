# Skip empty glass

Goal: segment only where there is tissue, so patches over empty glass are not run.

Where it sits in the pipeline: [Tiled segmentation](../how-it-works/tiling.md#in-this-pipeline).

## Steps

1. Switch it on in `params.yml`, with the mode for fluorescence:

   ```yaml
   use_tissue_segmentation: true
   mode: staining
   ```

2. Optionally steer it with [`level`](../reference/parameters.md#level), the pyramid level it
   reads (unset: the last, coarsest), and
   [`tissue_segmentation_kwargs`](../reference/parameters.md#tissue_segmentation_kwargs), a Python
   dict as text:

   ```yaml
   tissue_segmentation_kwargs: '{"channel": "DNA_1", "drop_threshold": 0.001}'
   ```

3. Run. `TISSUE_SEGMENTATION` takes the maximum over all channels (or `channel` alone),
   thresholds it with Otsu's method, and keeps pieces of at least `drop_threshold` (default 0.01)
   of the total tissue area. The outline is stored as `shapes/region_of_interest`; patches are
   clipped to it, and patches without tissue are dropped.
4. Check `region_of_interest` over the image in
   [the store](../outputs/visual-qc.md#id-3-the-spatialdata-store), and the QC report's "Cells
   per patch" map.

% source: nextflow_schema.json:269-286
% source: modules/local/utils.nf:41-47
% source: modules/local/tissue_segmentation/main.nf
% source: https://github.com/prism-oncology/sopa/blob/v2.2.9/sopa/cli/segmentation.py#L374-L400
% source: https://github.com/prism-oncology/sopa/blob/v2.2.9/sopa/segmentation/_tissue.py#L72 (level), #L148 (max), #L186 (drop_threshold)
% source: containers.tsv (python_sopa, sopa=2.2.9)
% source: workflows/histo.nf:70-88
% source: site/how-it-works/tiling.md#in-this-pipeline
% source: site/outputs/what-changes-it.md

## Pitfalls

- **Without `mode`, an image with exactly three channels** gets `saturation`, the H&E mode,
  which expects an 8-bit RGB image.
- **Use double quotes inside the dict.** The pipeline wraps the text in single quotes on the
  command line, so `{'channel': 'DNA_1'}` reaches sopa as `{channel: DNA_1}` and fails.
- **`channel` is a channel name in the store**: the marker sheet's `marker_name` with
  preprocessing; with pre-stitched input, the image's own channel names.
- **No tissue found** leaves 0 patches, and the run stops naming the sample.

% source: https://github.com/prism-oncology/sopa/blob/v2.2.9/sopa/segmentation/_tissue.py#L157-L166
% source: https://github.com/prism-oncology/sopa/blob/v2.2.9/sopa/segmentation/_tissue.py#L228-L230
% source: modules/local/utils.nf:4-38
% source: workflows/histo.nf:62,71-88
% source: subworkflows/local/segmentation/main.nf:34-40
