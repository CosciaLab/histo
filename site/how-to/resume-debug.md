# Resume and debug a run

Goal: find why a task failed, fix it, and continue without redoing finished work.

Nextflow's own account: [cache and
resume](https://www.nextflow.io/docs/latest/cache-and-resume.html), [`nextflow
log`](https://www.nextflow.io/docs/latest/reference/cli/log).

## Steps

1. Read the error Nextflow prints. It names the failed process, the command, its exit status,
   its error output and its work directory.
2. Go to that work directory and read, in this order:

   | File           | Holds                                                             |
   | -------------- | ----------------------------------------------------------------- |
   | `.command.err` | the task's error output                                           |
   | `.command.out` | its standard output; Ashlar's errors are here when `use_qc` is on |
   | `.command.log` | both, as the executor saw them                                    |
   | `.command.sh`  | the exact script that ran                                         |
   | `.exitcode`    | the exit status                                                   |

3. For errors outside a task, such as a sheet or parameter check at startup, read
   `.nextflow.log` in the launch directory.
4. To find failed tasks after the fact, list the runs, then filter one:

   ```bash
   nextflow log
   nextflow log <run_name> -f name,status,exit,workdir -F 'status == "FAILED"'
   ```

5. Fix the cause, then rerun the same command from the same launch directory with `-resume`.
   Finished tasks whose inputs and settings did not change are reused.

% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:214-216
% source: https://www.nextflow.io/docs/latest/executor.html (.command.sh, .command.run)
% source: https://www.nextflow.io/docs/latest/reference/cli/log
% source: https://www.nextflow.io/docs/latest/cache-and-resume.html
% source: Nextflow 26.10.4, a failing task run on 2026-11-05: the files listed and their contents

## Pitfalls

- **Keep `.nextflow/` and `work/`** in the launch directory: `-resume` needs both.
- **The store is changed in place.** `-resume` back to earlier parameters can reuse tasks that
  wrote a later store; rerun those samples without `-resume`. See
  [-resume and the store](../reference/usage.md#id-resume-and-the-store).
- **`nextflow log` cannot read a run that is still going.**
- **With `publish_dir_mode: symlink`** the results point into `work/`, and break when it is
  cleaned.

% source: https://www.nextflow.io/docs/latest/cache-and-resume.html
% source: docs/usage.md#id-resume-and-the-store
% source: site/outputs/what-changes-it.md
