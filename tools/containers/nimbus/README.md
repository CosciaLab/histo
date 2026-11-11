# Nimbus image (docker.io/josenimo/nimbus:0.0.5)

Nimbus-Inference 0.0.5 on `josenimo/sopa:2.3.0`, `V1.pt` baked in, no network at run time.

- Build: `docker buildx build --platform linux/amd64 -t docker.io/josenimo/nimbus:0.0.5 tools/containers/nimbus`
- Save: `docker save docker.io/josenimo/nimbus:0.0.5 -o nimbus_0.0.5.tar`
- Verify: `docker run --rm --network none --entrypoint python docker.io/josenimo/nimbus:0.0.5 -c "import numpy; from nimbus_inference.nimbus import Nimbus as N; n=N(dataset=None, output_dir='', save_predictions=False, device='cpu', checkpoint='V1.pt'); n.load_checkpoint(padding='valid'); print(numpy.__version__)"`
- Extra deps beyond the brief: `lxml` (pyometiff import), `huggingface_hub` with its own deps (needs `httpx2`).

## Findings (2026-11-11)

- **Numpy 2.** `import nimbus_inference.nimbus` works on numpy 2.5.4 (`--no-deps`).
- **CPU load.** `V1.pt` loads on CPU without `map_location`; no `map_location` is needed.
- **Halo.** Valid model, 1024 in, 836 out: raw `(1024-836)//2 = 94`; after upstream's `crop_by`
  (`836 % 32 = 4`) the output is 832, so the halo is `(1024-832)//2 = 96`. Use 96.
- **Magnification: not found.** Neither the paper nor the README gives the µm/px of "10x".
  The paper (Methods) says images are "resized to 1/4th of their original resolution" and tiled
  at 512 px, with no physical units. Issue
  [#61](https://github.com/angelolab/Nimbus-Inference/issues/61) (2026-05-22) asks whether MPP 1
  means `magnification=10`; the maintainer reply (2026-06-03) does not answer. "10x = 1 µm/px"
  stays an unconfirmed assumption. Ask the authors (jlrumber@stanford.edu) or test sensitivity.
- **Citation.** Rumberger JL, Greenwald NF, Ranek JS, et al. (20 authors, last: Angelo M).
  "Automated classification of cellular expression in multiplexed imaging data with Nimbus."
  Nature Methods 22(10):2161-2170, 2025. DOI 10.1038/s41592-025-02826-9
  (preprint bioRxiv 10.1101/2024.06.02.597062).

## Parity fixture (generated, not committed)

- Make: `uv run --python 3.11 --with tifffile --with numpy --with scikit-image --with scipy python -I tools/make_nimbus_fixture.py local_test_datasets/exemplar001/stitched/Exemplar001.ome.tif tests/unit/fixtures/nimbus_crop`
- Reference: `uv run --python 3.11 --with Nimbus-Inference==0.0.5 python -I tools/nimbus_reference.py tests/unit/fixtures/nimbus_crop`
- Crop: exemplar-001 stitched, rows 1000-2280, cols 600-1880; channels CD45 (dense), FOXP3 (sparse).
- Labels: no exemplar-001 segmentation exists on disk, so a quick scikit-image nuclei watershed
  on DNA_6, expanded 3 px (2683 cells). Not Cellpose; parity does not depend on label quality.
- The reference script uses `checkpoint="latest"`, which downloads `V1.pt` (the uv env has no
  local weights); same file as in the image. About 2.5 min on the Mac CPU.
