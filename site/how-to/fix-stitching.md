# Fix stitching

Goal: change Ashlar's arguments when the stitched image is misaligned, and rerun only what depends
on it.

Symptoms and what to try are in [When stitching or registration looks
wrong](../reference/usage.md#when-stitching-or-registration-looks-wrong).

## Steps

1. Find the symptom in the QC report's "Stitching and registration" section, or in
   `preprocessing/registration/{sample}_ashlar_qc/`, and pick a change from the table there.
2. Set [`ashlar_args`](../reference/parameters.md#ashlar_args) in `params.yml`. It replaces the
   default `--maximum-shift 30`, so repeat what you want to keep:

   ```yaml
   ashlar_args: "--maximum-shift 50 --filter-sigma 1"
   ```

3. To iterate fast, add `preprocessing_only: true`. Then check
   `{sample}_ashlar_qc/{sample}_ashlar_report.pdf` and the `overlay_cycleN.jpg` files; there is
   no HTML report.
4. Rerun from the same launch directory with `-resume`. BaSiCPy is reused, Ashlar runs again.
5. When stitching looks right, remove `preprocessing_only` and run again with `-resume`: Ashlar
   is reused.

% source: docs/usage.md#when-stitching-or-registration-looks-wrong
% source: nextflow_schema.json:65-70
% source: conf/modules.config:26-35
% source: docs/output.md#preprocessing
% source: docs/output.md:115-116
% source: workflows/histo.nf:66-67
% source: https://www.nextflow.io/docs/latest/cache-and-resume.html

## Pitfalls

- **`-c` must stay on a `dna` channel** in every cycle, or the run stops at startup. Set
  `skip_reference_dna_check: true` only if that is intended.
- **Do not pass `--qc-output` or `--report`**: the pipeline adds them with `use_qc`.
- **A poor alignment does not stop the run.** Check the report every time.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:458-500
% source: nextflow_schema.json:65-70
% source: site/how-it-works/ashlar.md#caveats
