"""Real-model tests for virtues_cells; run in the virtues image on a GPU, skipped elsewhere."""

import os

import numpy as np
import pytest

pytest.importorskip("virtues", reason="needs the virtues image")
pytest.importorskip("flash_attn", reason="needs the virtues image")
torch = pytest.importorskip("torch")
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")

import virtues_cells as vc  # noqa: E402

IDS = ["P08575", "P07766", "P05787"]  # CD45, CD3E, KRT8


@pytest.fixture(scope="module")
def encode():
    seqs = vc.uniprot_sequences(os.environ["VIRTUES_UNIPROT"], IDS)
    model = vc.load_virtues(os.environ["VIRTUES_WEIGHTS"], [seqs[i] for i in IDS], "cuda")
    return vc.virtues_encoder(model, len(IDS), "cuda")


def crops(n, seed=0):
    return np.random.default_rng(seed).normal(size=(n, len(IDS), vc.CROP, vc.CROP)).astype(np.float32)


def test_encoder_shape(encode):
    out = encode(crops(3))
    assert out.shape == (3, vc.GRID, vc.GRID, 512) and out.dtype == np.float32
    assert np.isfinite(out).all()
    assert encode(crops(0)).shape == (0, vc.GRID, vc.GRID, 512)


def test_determinism(encode):
    x = crops(5, seed=1)
    assert np.array_equal(encode(x), encode(x))
