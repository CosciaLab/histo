#!/usr/bin/env python3
"""Detect TMA cores at one Coreograph downsample factor, without writing core tiles.

One call per (slide, k). Runs UNetCoreograph's UNet and its TMA-mode post-processing on the
nuclear channel downsampled by 2^k, then scores the detected cores against the expected
count and diameter so COREOGRAPH_SELECT can pick k. Only the UNet step needs TensorFlow; the
rest is plain numpy and scikit-image.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import tifffile
import zarr
from skimage.measure import regionprops

# The Coreograph image keeps UNetCoreograph.py and its model in /app; overridable to run natively.
COREOGRAPH_APP = os.environ.get("COREOGRAPH_APP", "/app")
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


def detect_labels(img: np.ndarray, sensitivity: float, buffer: float) -> tuple[np.ndarray, float]:
    """Coreograph's TMA-mode detection on an already downsampled channel.

    Returns the core labels at that scale and Coreograph's estCoreDiam (downsampled px), the
    crop size it would use for every core.
    """
    from scipy.ndimage import distance_transform_edt
    from skimage.feature import blob_log
    from skimage.filters import gaussian
    from skimage.measure import label
    from skimage.morphology import remove_small_objects
    from skimage.segmentation import watershed

    sys.path.insert(0, COREOGRAPH_APP)
    from UNetCoreograph import getProbMaps

    # dsFactor 0: the image is already at 1/2^k, so getProbMaps must not halve it again.
    classProbs = getProbMaps(img, 0, str(Path(COREOGRAPH_APP) / "model"))

    # Copied from HMS-IDAC/UNetCoreograph 2.4.6, UNetCoreograph.py L1006-1039 (MIT). Keep in sync on bumps.
    # Changes: args.buffer became buffer, a noqa, and the empty-mask return below.
    preMask = gaussian(np.uint8(classProbs * 255), 1) > 0.8
    # Coreograph crashes on np.percentile([]) here; the sweep must survive a k that finds nothing.
    if not preMask.any():
        return np.zeros(preMask.shape, np.int32), 0.0

    P = regionprops(label(preMask), cache=False)
    area = [ele.area for ele in P]
    if len(P) < 3:
        medArea = np.median(area)
        maxArea = np.percentile(area, 99)
    else:
        count = 0
        labelpreMask = np.zeros(preMask.shape, dtype=np.uint32)
        for props in P:
            count += 1  # noqa: SIM113
            yi = props.coords[:, 0]
            xi = props.coords[:, 1]
            labelpreMask[yi, xi] = count
            P = regionprops(labelpreMask)
            area = [ele.area for ele in P]
        medArea = np.median(area)
        maxArea = np.percentile(area, 99)
    preMask = remove_small_objects(preMask, 0.2 * medArea)
    coreRad = round(np.sqrt(medArea / np.pi))
    estCoreDiam = round(np.sqrt(maxArea / np.pi) * 1.2 * buffer)

    # preprocessing
    fgFiltered = blob_log(preMask, coreRad * 0.6, threshold=sensitivity)
    Imax = np.zeros(preMask.shape, dtype=np.uint8)
    for iSpot in range(fgFiltered.shape[0]):
        yi = np.uint32(round(fgFiltered[iSpot, 0]))
        xi = np.uint32(round(fgFiltered[iSpot, 1]))
        Imax[yi, xi] = 1
    Imax = Imax * preMask
    Idist = distance_transform_edt(1 - Imax)
    markers = label(Imax)
    coreLabel = watershed(Idist, markers, watershed_line=True, mask=preMask)

    return coreLabel.astype(np.int32), float(estCoreDiam)


def write_overlay(path: Path, img: np.ndarray, labels: np.ndarray, title: str) -> None:
    """Core outlines and numbers on the channel, longest side at most 1024 px."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from skimage.segmentation import find_boundaries

    step = max(1, -(-max(img.shape) // 1024))
    thumb = img[::step, ::step].astype(float)
    top = np.percentile(thumb, 99.9) or 1.0
    rgb = np.repeat(np.clip(thumb / top, 0, 1)[..., None], 3, axis=2)
    rgb[find_boundaries(labels, mode="outer")[::step, ::step]] = (1.0, 0.2, 0.2)

    fig, ax = plt.subplots(figsize=(rgb.shape[1] / 100, rgb.shape[0] / 100 + 0.4), dpi=100)
    ax.imshow(rgb, interpolation="nearest")
    for p in regionprops(labels):
        ax.text(
            p.centroid[1] / step, p.centroid[0] / step, str(p.label), color="lime", ha="center", va="center"
        )
    ax.set_title(title)
    ax.axis("off")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--downsample-factor", type=int, required=True)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--sensitivity", type=float, default=0.3)
    parser.add_argument("--buffer", type=float, default=2.0)
    parser.add_argument("--expected-cores", type=int, required=True)
    parser.add_argument("--core-diameter-mm", type=float, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args(argv)
    k = args.downsample_factor
    out = f"{args.prefix}_k{k}"

    try:
        pixel_um = pixel_size_um(args.image)
        img = read_downsampled(args.image, args.channel, k)
    except ValueError as e:
        sys.exit(str(e))

    labels, est_core_diam_px = detect_labels(img, args.sensitivity, args.buffer)
    metrics = core_metrics(labels, est_core_diam_px, k, pixel_um, args.expected_cores, args.core_diameter_mm)
    metrics["pixel_um"] = pixel_um

    Path(f"{out}_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    # uint16, not Coreograph's uint8, so labels do not wrap above 255 cores.
    tifffile.imwrite(f"{out}_coremask.tif", labels.astype(np.uint16), compression="zlib")
    np.savetxt(f"{out}_centroids.txt", centroids_full_res(labels, k), fmt="%10.5f")
    write_overlay(Path(f"{out}_overlay.png"), img, labels, f"k={k}: {metrics['n_cores']} cores")


if __name__ == "__main__":
    main()
