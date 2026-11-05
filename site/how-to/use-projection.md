# Segment cells on many markers

Goal: let Cellpose see a whole mIF panel through two projected channels, nuclear and cell.
The method and its defaults are in
[Two-channel segmentation](../reference/usage.md#two-channel-segmentation-use-projection) and
[Channel projection](../how-it-works/projection.md).

## Steps

1. Mark the channels in the marker sheet. By default the first `dna` channel is `nuclear`, and
   every `marker` whose `channel_compartment` includes `membrane` or `cytoplasm` is `cell`. To
   choose by hand, add a `segmentation` column (`nuclear`, `cell` or `none`).
2. Set the projection and Cellpose's own thresholds in `params.yml`, and leave
   `cellpose_channels` unset:

   ```yaml
   use_cellpose: true
   use_projection: true
   flow_threshold: 0.4
   cellprob_threshold: 0
   clip_limit: 0
   ```

3. Run. Then open `qc/{sample}_projection.png`, what Cellpose saw, and look for a marker under
   `dominant` in `qc/{sample}_projection.json`.
4. If one marker dominates the `cell` channel, set its `segmentation` to `none` and run again.
5. To view the projection under the cell outlines, add `keep_projection: true`.

% source: docs/usage.md#inputs
% source: docs/usage.md#two-channel-segmentation-use-projection
% source: assets/schema_marker.json
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:670-676
% source: docs/output.md#qc-report

## Pitfalls

- **The `segmentation` column is all or nothing.** Once any row has a value, rows left blank are
  out of the projection, the `dna` channel included. Fill every channel you want.
- **Without the thresholds**, sopa's defaults tile the whole tissue into cells.
- **`-resume` after a run deleted the projection** fails; rerun without `-resume`. See
  [-resume and the store](../reference/usage.md#id-resume-and-the-store).
- At startup, the run stops if `nuclear` or `cell` would be empty.

% source: docs/usage.md#inputs
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:394-427
% source: docs/usage.md#two-channel-segmentation-use-projection
% source: docs/usage.md#id-resume-and-the-store
