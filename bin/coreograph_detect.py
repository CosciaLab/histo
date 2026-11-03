#!/usr/bin/env python3
"""Detect TMA cores at one Coreograph downsample factor, without writing core tiles.

One call per (slide, k). Runs UNetCoreograph's UNet and its TMA-mode post-processing on the
nuclear channel downsampled by 2^k, then scores the detected cores against the expected
count and diameter so COREOGRAPH_SELECT can pick k. Only the UNet step needs TensorFlow; the
rest is plain numpy and scikit-image.
"""

from pathlib import Path

import numpy as np
import tifffile
import zarr
from skimage.measure import regionprops

UM_PER_UNIT = {"µm": 1.0, "μm": 1.0, "um": 1.0, "nm": 1e-3, "mm": 1e3}


def read_downsampled(path: Path, channel: int, k: int) -> np.ndarray:
    """One channel at 1/2^k, read lazily.

    Coreograph halves the full channel k times with cv2 INTER_NEAREST, which maps output pixel
    i to input 2i; a strided read cropped to floor(shape / 2^k) gives the same pixels.
    """
    step = 2**k
    with tifffile.TiffFile(path) as tif:
        z = zarr.open(tif.series[0].aszarr(level=0), mode="r")
        if z.ndim == 2:
            data = z[::step, ::step]
        elif z.ndim == 3:
            data = z[channel, ::step, ::step]
        else:
            raise ValueError(f"{path}: expected a YX or CYX image, got shape {z.shape}")
        h, w = z.shape[-2:]
    return np.asarray(data)[: h >> k, : w >> k]


def pixel_size_um(path: Path) -> float:
    """PhysicalSizeX in µm from the OME-XML of the first image."""
    with tifffile.TiffFile(path) as tif:
        xml = tif.ome_metadata
    image = tifffile.xml2dict(xml).get("OME", {}).get("Image", {}) if xml else {}
    pixels = (image[0] if isinstance(image, list) else image).get("Pixels", {})
    if "PhysicalSizeX" not in pixels:
        raise ValueError(
            f"{path}: no pixel size (PhysicalSizeX) in the OME-XML, so the core diameter in mm "
            "cannot be compared. Set coreograph_args to choose the downsample factor yourself."
        )
    unit = pixels.get("PhysicalSizeXUnit", "µm")
    if unit not in UM_PER_UNIT:
        raise ValueError(f"{path}: pixel size unit {unit!r} is not one of {sorted(UM_PER_UNIT)}")
    return float(pixels["PhysicalSizeX"]) * UM_PER_UNIT[unit]


def core_metrics(
    labels: np.ndarray,
    est_core_diam_px: float,
    k: int,
    pixel_um: float,
    expected_cores: int,
    diameter_mm: float,
) -> dict:
    """Score one factor's core labels (at the downsampled scale) against the expectation."""
    mm_per_px = 2**k * pixel_um / 1000
    areas = np.bincount(labels.ravel())[1:]
    areas = areas[areas > 0]
    n = int(areas.size)
    metrics = {
        "k": k,
        "n_cores": n,
        "count_error": abs(n - expected_cores) / expected_cores,
        "diam_mm": None,
        "diam_error": None,
        "size_cv": None,
        "crop_ratio": None,
        "core_px_at_k": diameter_mm / mm_per_px,
        "um_per_px": pixel_um * 2**k,
    }
    if n:
        diam_mm = float(np.median(2 * np.sqrt(areas / np.pi))) * mm_per_px
        metrics["diam_mm"] = diam_mm
        metrics["diam_error"] = abs(diam_mm - diameter_mm) / diameter_mm
        metrics["size_cv"] = float(areas.std() / areas.mean())
        metrics["crop_ratio"] = est_core_diam_px * mm_per_px / diameter_mm
    return metrics


def centroids_full_res(labels: np.ndarray, k: int) -> np.ndarray:
    """(y, x) per label in full-resolution pixels, computed as Coreograph does."""
    ds_factor = 1 / 2**k
    centroids = [p.centroid for p in regionprops(labels)]
    return np.array(centroids, dtype=float).reshape(-1, 2) / ds_factor
