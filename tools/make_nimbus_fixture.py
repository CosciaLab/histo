"""Cut the Nimbus parity fixture from a stitched OME-TIFF (CYX).

Usage: python -I tools/make_nimbus_fixture.py <stitched.ome.tif> <out_dir> [size [y0 x0]]
Needs numpy, tifffile, scikit-image, scipy (e.g. `uv run --with ...`).
Writes image.npy (C,Y,X uint16) and labels.npy (int32).
"""

import sys
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.filters import gaussian, threshold_otsu
from skimage.segmentation import expand_labels, watershed

# 0-based channels of exemplar-001 (markers_exemplar001.csv): DNA_6, CD45 (dense), FOXP3 (sparse).
DNA, CHANNELS = 0, (3, 10)
Y0, X0, SIZE = 1000, 600, 1280
EXPAND_PX = 3


def whole_cell_labels(dna):
    """Quick nuclei watershed expanded to whole cells. Parity does not depend on its quality."""
    smooth = gaussian(dna.astype(np.float32), 2)
    fg = smooth > threshold_otsu(smooth)
    dist = ndi.distance_transform_edt(fg)
    peaks = peak_local_max(gaussian(dist, 1), min_distance=5, labels=fg)
    markers = np.zeros(dna.shape, np.int32)
    markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
    nuclei = watershed(-dist, markers, mask=fg)
    return expand_labels(nuclei, EXPAND_PX).astype(np.int32)


def main(src, out_dir, size=SIZE, y0=Y0, x0=X0):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stack = tifffile.imread(src)
    win = (slice(y0, y0 + size), slice(x0, x0 + size))
    image = np.stack([stack[c][win] for c in CHANNELS]).astype(np.uint16)
    labels = whole_cell_labels(stack[DNA][win])
    np.save(out / "image.npy", image)
    np.save(out / "labels.npy", labels)
    print(
        f"image {image.shape} {image.dtype}, labels {labels.shape} {labels.dtype}, "
        f"{len(np.unique(labels)) - 1} cells"
    )


if __name__ == "__main__":
    main(*sys.argv[1:3], *map(int, sys.argv[3:6]))
