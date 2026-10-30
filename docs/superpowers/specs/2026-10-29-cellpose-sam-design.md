# Cellpose-SAM replaces Cellpose 3

ROADMAP 1.4 items 1 and 3. One segmentation backend per run, as now.

## Goal

`use_cellpose` runs Cellpose-SAM (`cpsam`) instead of Cellpose 3 (`cyto3`). Success: the test
profile and both cluster exemplars produce a normal store and table with CPSAM; stub and
validation nf-tests pass.

## Why it is small

sopa has no separate CPSAM method. `sopa segmentation cellpose` checks the installed cellpose:
with ≥ 4 it ignores `model_type`, defaults `pretrained_model` to `cpsam` and accepts 3
channels. Resolve, the `cellpose_boundaries` key, `AGGREGATE` and `use_projection` are
unchanged. Only the image changes: `docker.io/josenimo/sopa:2.2.12` (cellpose 4.2.1.1, weights
baked in).

## Changes

1. **Container.** `PATCH_SEGMENTATION_CELLPOSE` and `RESOLVE_CELLPOSE` use the static URI
   `docker.io/josenimo/sopa:2.2.12`, like InstanSeg. Update their `environment.yml`; regenerate
   `containers.tsv`, which drops the Seqera `python_sopa_cellpose` image.
2. **Weights.** Remove `export CELLPOSE_LOCAL_MODELS_PATH=./cellpose_cache`. Cellpose reads
   `$CELLPOSE_LOCAL_MODELS_PATH`, else `~/.cellpose/models`; Apptainer mounts the user's home,
   so the image must set the variable. Inspect the image first; if unset, export the in-image
   path in the module.
3. **Parameters** (schema via `nf-core pipelines schema build` only):
   - Remove `cellpose_diameter`. sopa's CLI requires `--diameter`, so `extractSubArgs` passes
     `30`: cellpose 4 rescales by `30 / diameter`, so 30 equals no diameter.
   - Remove `cellpose_model_type`; cellpose 4 ignores it.
   - Keep `pretrained_model` (unset means `cpsam`; a path allows fine-tuned weights),
     thresholds, CLAHE, `cellpose_channels`, `cellpose_use_gpu` (default false).
   - The strict parameter check then rejects old configs that set the removed params.
4. **versions.yml.** Read cellpose's version with `importlib.metadata`, as InstanSeg does.
5. **Resources.** Keep `process_single`; choose the label from the first cluster run.

## Tests

- Remove `cellpose_diameter` from `conf/test*.config`; update `tests/args_cli.nf.test` if it
  asserts on diameter or model type.
- Stubs unchanged: outputs are identical.
- Mac: one real `-profile test` run with the 2.2.12 image, if it runs under Rosetta.
- Cluster: both exemplar runs; re-baseline expected cell counts from them.

## Docs

- CHANGELOG: breaking. cyto3, `cellpose_diameter` and `cellpose_model_type` removed; slower
  per patch.
- `usage.md`: drop `cellpose_diameter` and `cellpose_model_type` from the table and examples.
- `decisions.md`: one line on replacing Cellpose 3.
- CITATIONS: Cellpose-SAM paper.
- ROADMAP: mark 1.4 items 1 and 3 done.
- No graph change, so no metro-map re-render.

## Out of scope

GPU on SLURM (next change), three-channel projection (ROADMAP 1.3), multiple segmentations.

## Risk

CPU time. The benchmark measured CPSAM at ~24 s per 1200 px crop on Apple MPS (GPU) against
3 s for cyto3; CPU will be slower still. WSI runs will be slow until the GPU change lands.
