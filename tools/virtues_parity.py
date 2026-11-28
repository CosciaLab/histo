#!/usr/bin/env python3
"""Parity of our VirTues runner with upstream on the bundled example core; run in the virtues image on a GPU.

Upstream runs as notebook 2_demo_cell_phenotyping (spora-io standardiser with the blur, 120 px pad,
compute_cell_tokens) at chunk_size 32 and 8. Ours runs cell_embeddings on the same raw image, mask and
statistics (through a virtues_stats.json), with the bundled marker embeddings, so only the runner is
compared; our ESM-2 embeddings of the same IDs are compared with the bundled ones separately.
--cpu-only stops before the model (no FlashAttention on CPU): input and ESM-2 only.

Usage: virtues_parity.py OUT.json [--cpu-only]
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import virtues_cells as vc  # noqa: E402
import virtues_stats as vs  # noqa: E402

TISSUE_ID = "cords2024cancer_ocmzljpb_0001"  # the bundled example core


def compare(a, b):
    """Per-row cosine (min, median) and max abs difference of two (n, D) arrays."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    return {
        "n": len(a),
        "cosine_min": float(cos.min()),
        "cosine_median": float(np.median(cos)),
        "max_abs_diff": float(np.abs(a - b).max()),
    }


def upstream_inputs(src):
    """Notebook 2 up to the standardised input: dataset, tissue, padded mask, x, channel metadata."""
    import torch
    from omegaconf import OmegaConf
    from spora_io import MultiplexImagingDataset

    conf = OmegaConf.load(f"{src}/configs/base_config.yaml")
    c = OmegaConf.load(f"{src}/configs/datasets/example_config.yaml")["datasets"]["example_dataset"]
    ds = MultiplexImagingDataset(
        name=c.name,
        path=str(Path(src) / c.path),
        modality=c.modality,
        standardization=c.standardization,
        resolution=c.resolution,
        tile_size=conf.data.tile_size,
        disable_quantile_mask=True,
        filter_list=["gaussian_blur"],
        use_mean_std=True,
    )
    t = ds.get_tissue(tissue_id=TISSUE_ID, kind="uniprot_filtered", preprocess=False)
    pad = (vc.PAD,) * 4
    x = torch.nn.functional.pad(t.image, pad=pad, mode="constant", value=0)
    mask = torch.nn.functional.pad(
        ds.get_cell_instance_mask(TISSUE_ID).mask, pad=pad, mode="constant", value=0
    )
    x, refined = ds.standardizer.apply(x, TISSUE_ID, t.measured_mask, t.image_loading_mask)
    _, names, ids = ds._refine_channel_metadata(t.image_loading_mask, t.channel_names, t.uniprot_ids, refined)
    # notebook 2 indexes markers with the unrefined IDs, so its recipe holds only if nothing was dropped
    if list(ids) != list(t.uniprot_ids) or x.shape[0] != len(ids):
        sys.exit(f"standardiser dropped channels: {list(t.uniprot_ids)} -> {list(ids)}")
    stats = [
        s.flatten().numpy() for s in ds.standardizer._get_cached_stats(TISSUE_ID, t.measured_mask, refined)
    ]
    return t, mask, x, list(names), list(ids), stats


def our_source(mask):
    """CellSource from a padded instance mask: compact labels 1..n, centroids and boxes from its pixels."""
    ids = np.unique(mask)
    ids = ids[ids > 0]
    labels = np.where(mask > 0, np.searchsorted(ids, mask) + 1, 0).astype(np.int32)
    ys, xs = np.nonzero(labels)
    lab = labels[ys, xs] - 1
    n = len(ids)
    count = np.bincount(lab, minlength=n)
    centroids = np.stack([np.bincount(lab, ys, n) / count, np.bincount(lab, xs, n) / count], axis=1)
    bboxes = np.zeros((n, 4), dtype=np.int64)
    bboxes[:, 0], bboxes[:, 2] = ys.max() + 1, xs.max() + 1
    np.minimum.at(bboxes[:, 0], lab, ys)
    np.maximum.at(bboxes[:, 1], lab, ys + 1)
    np.minimum.at(bboxes[:, 2], lab, xs)
    np.maximum.at(bboxes[:, 3], lab, xs + 1)
    return ids, vc.CellSource(lambda y0, y1, x0, x1: labels[y0:y1, x0:x1], centroids, bboxes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", help="JSON report")
    ap.add_argument("--cpu-only", action="store_true", help="input and ESM-2 only, no model")
    args = ap.parse_args(argv)
    import torch
    from virtues.utils.utils import load_marker_embedding_dict, load_marker_embeddings

    src = os.environ["VIRTUES_SRC"]
    emb_dir = f"{src}/assets/example_dataset/marker_embeddings"
    device = "cpu" if args.cpu_only else "cuda"
    report = {
        "tissue_id": TISSUE_ID,
        "virtues_commit": os.environ.get("VIRTUES_COMMIT", "unknown"),
        "torch": torch.__version__,
        "gpu": None if args.cpu_only else torch.cuda.get_device_name(0),
    }

    t, mask, x, names, ids, (upper, lower, mean, std) = upstream_inputs(src)
    if np.any(lower != 0):
        sys.exit(f"upstream lower quantiles are not 0 ({lower}); our runner clips only from above")
    raw = t.image.numpy()
    report.update(n_channels=len(ids), padded_shape=list(mask.shape), raw_min=float(raw.min()))

    # the statistics upstream used, through our statistics file format and loader
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{TISSUE_ID}_virtues_stats.json"
        markers = {
            n: {"uniprot_id": u, "cap": float(c), "mean": float(m), "sd": float(s), "tissue_pixels": 0}
            for n, u, c, m, s in zip(names, ids, upper, mean, std, strict=True)
        }
        path.write_text(json.dumps({"format": vs.STATS_FORMAT, "slide": TISSUE_ID, "markers": markers}))
        st = vc.stats_arrays(vs.load_stats(path, list(zip(names, ids, strict=True))), names)
    padded = tuple(mask.shape)

    def read_raw(c, y0, y1, x0, x1):
        # upstream clamps from below at its lower quantile, 0
        return np.maximum(vs.resample_window(raw, c, y0, y1, x0, x1, 1.0), 0)

    def read_input(y0, y1, x0, x1):
        return vc.model_input(read_raw, st, y0, y1, x0, x1, padded)

    report["input_max_abs_diff"] = float(np.abs(read_input(0, padded[0], 0, padded[1]) - x.numpy()).max())

    bundled = load_marker_embeddings(emb_dir)
    emb_dict = load_marker_embedding_dict(emb_dir)
    midxs = torch.tensor([emb_dict[u] for u in ids], dtype=torch.long)
    # ruling R4: UniProt changed some sequences since the bundled embeddings, so report ESM-2 alone
    seqs = vc.uniprot_sequences(os.environ["VIRTUES_UNIPROT"], sorted(set(ids)))
    ours_esm = vc.esm_embeddings([seqs[u] for u in ids], device)
    diff = (ours_esm - bundled[midxs]).abs().amax(dim=1).numpy()
    report["esm_max_abs_diff"] = float(diff.max())
    report["esm_markers_over_1e-5"] = {u: float(d) for u, d in zip(ids, diff, strict=True) if d > 1e-5}

    if not args.cpu_only:
        from safetensors.torch import load_file
        from virtues.modules.multiplex_virtues import MultiplexVirtues
        from virtues.utils.cell_tokens import compute_cell_tokens

        weights = os.environ["VIRTUES_WEIGHTS"]
        up_model = MultiplexVirtues(prior_bias_embeddings=bundled)  # notebook 2, cells 4 and 6
        up_model.load_state_dict(load_file(weights, device="cuda"))
        up_model = up_model.cuda().eval()
        up = {}
        for chunk in (32, 8):
            cell_ids, tokens, _, _ = compute_cell_tokens(up_model, x, midxs, mask, chunk_size=chunk)
            up[chunk] = (cell_ids.numpy(), tokens.float().numpy())
        if not np.array_equal(up[32][0], up[8][0]):
            sys.exit("upstream's cells differ between chunk sizes")
        del up_model

        cell_ids, source = our_source(mask.numpy())
        if not np.array_equal(cell_ids, up[32][0]):
            sys.exit("upstream's cells differ from the mask's labels")
        encode = vc.virtues_encoder(vc.build_model(weights, bundled[midxs], device), len(ids), device)
        ours = {}
        for run, tile, batch in [("b32", vc.TILE, 32), ("b8", vc.TILE, 8), ("t512", 512, 32)]:
            out = vc.cell_embeddings(read_input, {"cells": source}, padded, encode, tile=tile, batch=batch)
            ours[run] = out["cells"][0]
        report.update(
            n_cells=len(cell_ids),
            upstream_chunk32_vs_chunk8=compare(up[32][1], up[8][1]),
            ours_vs_upstream=compare(ours["b32"], up[32][1]),
            ours_batch32_vs_batch8=compare(ours["b32"], ours["b8"]),
            ours_tile512_vs_tile2048=compare(ours["t512"], ours["b32"]),
        )

    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
