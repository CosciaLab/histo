# Run without internet

Goal: run on a cluster without network access at run time. Every image is staged in advance;
the pipeline pulls nothing while it runs. Commands:
[Fetching images](../reference/usage.md#fetching-images) and
[Staging images into the shared cache](../reference/usage.md#staging-images-into-the-shared-cache).

## Steps

1. On a Linux machine with internet, download the pipeline and its images with
   `nf-core pipelines download`, once per release.
2. Cross-check the download against
   [`containers.tsv`](https://github.com/CosciaLab/histo/blob/dev/containers.tsv), which lists
   every image the pipeline uses, one row per image.
3. Set `NXF_SINGULARITY_CACHEDIR` in your own environment, for example in `~/.bashrc`:

   ```bash
   export NXF_SINGULARITY_CACHEDIR=/path/to/cache
   ```

4. Copy only the images the cache lacks, with `rsync --ignore-existing`.
5. Launch with `export NXF_OFFLINE=true` and `-profile singularity,…`, as in
   [Running on the cluster](../reference/usage.md#running-on-the-cluster).

% source: docs/usage.md#fetching-images
% source: docs/usage.md#staging-images-into-the-shared-cache
% source: docs/usage.md#running-on-the-cluster
% source: docs/CONTRIBUTING.md#containers
% source: tools/container_manifest.py:1-7
% source: conf/slurm.config:36-40

## Pitfalls

- **Never delete or overwrite an image in a shared cache.** Colleagues' running jobs use it.
- **The pipeline sets no cache directory.** Set `NXF_SINGULARITY_CACHEDIR` in the shell you
  launch from.
- **Five images are Docker-only** and are converted while downloading, which is slower and subject
  to Docker Hub's rate limits.

% source: docs/usage.md#staging-images-into-the-shared-cache
% source: conf/slurm.config:38
% source: docs/CONTRIBUTING.md#what-the-pipeline-needs
