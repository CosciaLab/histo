# At the MDC

## The dropbox

The MDC dropbox runs the pipeline on the cluster for you. Drop a `<name>_samplesheet.csv` into your
dropbox folder; results appear in your `output` folder. Images stay where they are.

- **Settings:** an optional `<name>_params.yml` next to the samplesheet takes this site's
  [parameters](reference/parameters.md). Without it, the lab defaults are used.
- **Resources:** `size:` in the params file (`tiny`, `small` or `medium`) sets how many cluster
  resources the run gets. For larger images, ask Jose.
- **Not accepted** in the params file, because the dropbox sets them: `input`, `outdir`, every
  path-type parameter, `custom_config_*`, and `pretrained_model`, `publish_dir_mode`, `email`,
  `email_on_fail`, `plaintext_email`, `pipelines_testdata_base_path`, `config_profile_name`,
  `config_profile_description`, `config_profile_contact`, `config_profile_url`, `help`,
  `help_full`, `show_hidden`, `version`, `validate_params`.
- **One samplesheet, one run.** Editing a sheet after it was picked up does nothing; to run again,
  save it under a new name.

% source: histo-dropbox docs/USER_GUIDE.md
% source: histo-dropbox config/blocked_params.yml
% source: conf/sizes.config

A `<name>_STATUS.txt` appears next to the samplesheet within a few minutes. Its first line:

| Status              | Meaning                                                                        |
| ------------------- | ------------------------------------------------------------------------------ |
| QUEUED              | All checks passed; waiting for a free slot.                                    |
| SUBMITTED / RUNNING | On the cluster. Large datasets take hours.                                     |
| COMPLETED           | Done; results are in your `output` folder.                                     |
| INVALID             | The samplesheet or params are wrong; the file lists each problem. Nothing ran. |
| FAILED              | The pipeline stopped; the file shows why.                                      |

% source: histo-dropbox docs/USER_GUIDE.md

The full user guide, with the samplesheet path rules, is in the private histo-dropbox repository;
or ask Jose.

## Running it yourself

On the MDC cluster add `slurm,mdc` to the profiles, e.g.
`-profile singularity,size_small,slurm,mdc`. See [Profiles](reference/usage.md#profiles).

% source: docs/usage.md#profiles
% source: conf/mdc.config
