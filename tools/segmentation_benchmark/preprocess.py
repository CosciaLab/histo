"""Crop preprocessing for the segmentation benchmark, equal to the pipeline's.

project() mirrors bin/project_channels.py (percentiles, rescale, Gaussian, combine, uint16) so
benchmark results transfer; the percentiles come from the crop itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin"))

from project_channels import combine, percentile_bounds, rescale  # noqa: E402

# Nuclear-localised markers in the Cross-platform and CODEX panels; left out of `membrane`.
NUCLEAR_MARKERS = {"ki67", "foxp3", "tcf1", "tox", "mum1", "pax8", "p63"}
SELECTIONS = ("all", "markers", "membrane")


def _marker(name: str) -> str:
    """'Foxp3 (Opal 620)' -> 'foxp3'."""
    return name.split("(")[0].strip().lower().replace("-", "")


def cell_channels(names: list[str], nuclear: int, selection: str) -> list[int]:
    """Indices combined into the cell plane: every non-DNA channel, minus autofluorescence
    (`markers`), minus nuclear-localised markers too (`membrane`)."""
    if selection not in SELECTIONS:
        raise ValueError(f"unknown cell channel selection {selection!r}; expected one of {SELECTIONS}")
    keep = []
    for i, name in enumerate(names):
        marker = _marker(name)
        if i == nuclear:
            continue
        if selection != "all" and marker.startswith("autofluorescence"):
            continue
        if selection == "membrane" and marker in NUCLEAR_MARKERS:
            continue
        keep.append(i)
    if not keep:
        raise ValueError(f"no cell channels left for selection {selection!r} in {names}")
    return keep


def _group(planes: np.ndarray, method: str, low: float, high: float, sigma: float) -> np.ndarray:
    """One projected plane as uint16; flat channels are left out, none left gives zeros."""
    from scipy.ndimage import gaussian_filter

    stack = []
    for plane in planes:
        bounds = percentile_bounds(plane, low, high)
        if bounds is None:
            continue
        x = rescale(plane, *bounds)
        stack.append(gaussian_filter(x, sigma) if sigma > 0 else x)
    if not stack:
        return np.zeros(planes.shape[1:], np.uint16)
    return (combine(np.stack(stack), method) * 65535 + 0.5).astype(np.uint16)


def project(
    image: np.ndarray,
    nuclear: int,
    method: str,
    low: float,
    sigma: float,
    high: float = 99.9,
    cell_idx: list[int] | None = None,
) -> np.ndarray:
    """(2, Y, X) uint16 [cell, nuclear]; cell is `cell_idx`, by default every channel but `nuclear`."""
    cells = np.delete(image, nuclear, axis=0) if cell_idx is None else image[cell_idx]
    return np.stack(
        [_group(cells, method, low, high, sigma), _group(image[[nuclear]], method, low, high, sigma)]
    )


def sopa_preprocess(image, gaussian_sigma: float, clip_limit: float):
    """sopa.segmentation.stainings._run_patch, before the model."""
    from scipy.ndimage import gaussian_filter
    from skimage import exposure

    if gaussian_sigma > 0:
        image = np.stack([gaussian_filter(c, sigma=gaussian_sigma) for c in image])
    if clip_limit > 0:
        image = np.stack([exposure.equalize_adapthist(c, clip_limit=clip_limit) for c in image])
    return image


def pad_to(image: np.ndarray, size: int = 256) -> tuple[np.ndarray, tuple[int, int]]:
    """Reflect-pad (C, Y, X) at the bottom/right to at least `size`; also return the old (Y, X)."""
    y, x = image.shape[1:]
    pad = ((0, 0), (0, max(0, size - y)), (0, max(0, size - x)))
    return np.pad(image, pad, mode="reflect"), (y, x)


def unpad(labels: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Crop labels back to `shape` and renumber them 1..n."""
    from skimage.segmentation import relabel_sequential

    return relabel_sequential(labels[: shape[0], : shape[1]])[0]
