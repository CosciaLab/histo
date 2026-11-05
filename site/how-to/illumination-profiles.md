# Reuse illumination profiles

Goal: give Ashlar profiles from an earlier run, so BaSiCPy does not run again. Within one launch
directory `-resume` already reuses them; this is for a new run. What BaSiCPy computes:
[Illumination correction](../how-it-works/basicpy.md).

## Steps

1. Find the earlier run's profiles: `preprocessing/illumination/{sample}_cycle{n}-dfp.ome.tif`
   and `-ffp.ome.tif`, one pair per cycle. Each file holds one plane per channel of that cycle.
2. Add `dfp` and `ffp` columns to the samplesheet, with absolute paths, on every cycle row of
   the sample:

   ```csv
   sample,cycle_number,image_tiles,dfp,ffp,marker_sheet
   slide01,1,/data/raw/slide01/cycle01.ome.tiff,/data/run1/preprocessing/illumination/slide01_cycle1-dfp.ome.tif,/data/run1/preprocessing/illumination/slide01_cycle1-ffp.ome.tif,/data/sheets/markers_slide01.csv
   slide01,2,/data/raw/slide01/cycle02.ome.tiff,/data/run1/preprocessing/illumination/slide01_cycle2-dfp.ome.tif,/data/run1/preprocessing/illumination/slide01_cycle2-ffp.ome.tif,/data/sheets/markers_slide01.csv
   ```

3. Run. BaSiCPy is skipped for those cycles, and nothing new is written to
   `preprocessing/illumination/` for them.

% source: docs/output.md#preprocessing
% source: bin/basicpy_main.py:322-335
% source: conf/modules.config:15-24
% source: assets/schema_input_cycle.json
% source: subworkflows/local/preprocess_images/main.nf:19-35
% source: https://www.nextflow.io/docs/latest/cache-and-resume.html

## Pitfalls

- **Every cycle of a sample or none.** A sample with profiles on some cycles stops at startup.
- **Match the channels.** A profile has one plane per channel, in that cycle's order; reuse it
  only for a cycle acquired with the same channels in the same order.
- **The dark-field profile is not fitted** by this pipeline; see the
  [caveats](../how-it-works/basicpy.md#caveats).

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:225-237
% source: bin/basicpy_main.py:262-335
% source: site/how-it-works/basicpy.md#caveats
