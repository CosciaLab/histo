# Segment on a GPU

Goal: run the Cellpose and InstanSeg patch tasks on GPUs on the cluster. What `use_gpu` does is
in [GPU segmentation](../reference/usage.md#gpu-segmentation).

## Steps

1. Add `use_gpu: true` to `params.yml`.
2. With InstanSeg, keep it at 10 channels or fewer: name them in
   [`instanseg_channels`](../reference/parameters.md#instanseg_channels), for example
   `"DNA_1 CD45 PanCK CD3 CD8"`. The run checks this at startup.
3. Run with the `slurm` profile. Each patch task then asks SLURM for `--gres=gpu:1`; with `mdc`
   as well, an A40 in the `gpu` partition.
4. On another cluster whose GPUs sit in their own partition, give it in a config file with `-c`:

   ```groovy
   process {
       withName: 'SEGMENT_PATCH_(CELLPOSE|INSTANSEG)' {
           queue = 'gpu'
       }
   }
   ```

5. Check one patch task's `.command.out`: its `[segment_patch]` line ends with `device cuda`.

% source: docs/usage.md#gpu-segmentation
% source: conf/gpu.config
% source: conf/slurm.config:16-17
% source: conf/mdc.config:11-14
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:378-389
% source: subworkflows/local/utils_nfcore_histo_pipeline/main.nf:678-683
% source: docs/usage.md:13-14
% source: bin/segment_patch.py:144
% source: modules/local/segment_patch/main.nf:19-21

## Pitfalls

- **No silent CPU fallback.** A task without a usable GPU fails with
  `use_gpu: CUDA is not usable in this task` in `.command.err`.
- **Not on the Mac**: Docker there has no GPU.
- **At most 16 patches per method run at once**, so a run cannot take every free GPU.

% source: modules/local/segment_patch/main.nf:19
% source: docs/usage.md#gpu-segmentation
% source: conf/gpu.config
