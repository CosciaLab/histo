# ruff: noqa: E402, PTH208, PTH123, PTH118, SIM115
# Container script: imports are deferred on purpose and plain os/open is fine.
"""Check the VirTues image. --cpu-only skips everything that needs CUDA (flash_attn, the forward pass)."""

import argparse
import importlib
import os
import sys

import torch

ap = argparse.ArgumentParser()
ap.add_argument("--cpu-only", action="store_true")
args = ap.parse_args()

SRC = os.environ["VIRTUES_SRC"]
EMB_DIR = f"{SRC}/assets/example_dataset/marker_embeddings"

print("python", sys.version.split()[0], "torch", torch.__version__, "cuda", torch.version.cuda)
for mod in ("spatialdata", "anndata", "geopandas", "esm", "virtues", "spora_io"):
    m = importlib.import_module(mod)
    print(mod, getattr(m, "__version__", "(no __version__)"))
print("uniprot release", os.environ["VIRTUES_UNIPROT_RELEASE"], "commit", os.environ["VIRTUES_COMMIT"])

# Mac emulation has no CUDA driver; upstream imports flash_attn unconditionally, so this may fail there.
model = None
try:
    from virtues.modules.multiplex_virtues import MultiplexVirtues
    from virtues.utils.utils import load_marker_embedding_dict, load_marker_embeddings
    from safetensors.torch import load_file

    emb = load_marker_embeddings(EMB_DIR)
    model = MultiplexVirtues(prior_bias_embeddings=emb)
    print("load_state_dict:", model.load_state_dict(load_file(os.environ["VIRTUES_WEIGHTS"]), strict=True))
except ImportError as e:
    if not args.cpu_only:
        raise
    print("SKIPPED model load on CPU, import failed:", e)

# Our ESM-2 embedding of each bundled ID vs the bundled .pt (upstream: mean of layer-30 residue tokens).
import esm

ids = sorted(f[:-3] for f in os.listdir(EMB_DIR) if f.endswith(".pt"))
seqs, name = {}, None
for line in open(os.environ["VIRTUES_UNIPROT"]):
    if line.startswith(">"):
        name = line.split("|")[1]
        seqs[name] = []
    else:
        seqs[name].append(line.strip())
esm_model, alphabet = esm.pretrained.load_model_and_alphabet("esm2_t30_150M_UR50D")
esm_model.eval()
conv = alphabet.get_batch_converter()
worst = 0.0
for i in ids:
    seq = "".join(seqs[i])
    _, _, tok = conv([(i, seq)])
    with torch.no_grad():
        rep = esm_model(tok, repr_layers=[30])["representations"][30][0, 1 : len(seq) + 1].mean(0)
    d = (rep - torch.load(f"{EMB_DIR}/{i}.pt", weights_only=True)).abs().max().item()
    worst = max(worst, d)
    print(f"esm {i} len={len(seq)} max_abs_diff={d:.3e}")
print("esm max_abs_diff over", len(ids), "markers:", f"{worst:.3e}")

if args.cpu_only:
    print("OK (cpu-only)")
    sys.exit(0)

# Cluster path: as notebook 2_demo_cell_phenotyping.ipynb.
import flash_attn
from omegaconf import OmegaConf
from spora_io import MultiplexImagingDataset
from virtues.utils.cell_tokens import compute_cell_tokens

print("flash_attn", flash_attn.__version__, "gpu", torch.cuda.get_device_name(0))
model = model.cuda().eval()
conf = OmegaConf.load(f"{SRC}/configs/base_config.yaml")
c = OmegaConf.load(f"{SRC}/configs/datasets/example_config.yaml")["datasets"]["example_dataset"]
ds = MultiplexImagingDataset(
    name=c.name,
    path=os.path.join(SRC, c.path),
    modality=c.modality,
    standardization=c.standardization,
    resolution=c.resolution,
    tile_size=conf.data.tile_size,
    disable_quantile_mask=True,
    filter_list=["gaussian_blur"],
    use_mean_std=True,
)
tid = "cords2024cancer_ocmzljpb_0001"
t = ds.get_tissue(tissue_id=tid, kind="uniprot_filtered", preprocess=False)
emb_dict = load_marker_embedding_dict(EMB_DIR)
midxs = torch.tensor([emb_dict[u] for u in t.uniprot_ids], dtype=torch.long)
mask = ds.get_cell_instance_mask(tid).mask
pad = (120, 120, 120, 120)
x = torch.nn.functional.pad(t.image, pad=pad)
mask = torch.nn.functional.pad(mask, pad=pad)
x, refined = ds.standardizer.apply(x, tid, t.measured_mask, t.image_loading_mask)
ds._refine_channel_metadata(t.image_loading_mask, t.channel_names, t.uniprot_ids, refined)
cell_ids, tokens, crop_tokens, idx = compute_cell_tokens(model, x, midxs, mask)
print("image", tuple(x.shape), "crops", len(idx), "channels", len(midxs))
print("patch_summary_tokens per crop:", tuple(crop_tokens[0].shape), crop_tokens[0].dtype)
print("cell_tokens:", tuple(tokens.shape), tokens.dtype, "cells", len(cell_ids))
print("OK (cluster)")
