#!/usr/bin/env python3
"""Polygon-exact shape features for cells and nuclei, in pixel units.

Area, perimeter, circularity (4*pi*A/P^2), solidity (area / convex hull area) and the
ellipse-equivalent axes and eccentricity, from the second central moments of the polygon
(holes subtract, MultiPolygon parts sum), defined as in skimage.measure.regionprops.
Circularity is NaN below MIN_CIRCULARITY_AREA, where pixel-scale noise dominates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Heavy libraries are imported inside functions so the module imports without them.
if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd
    from shapely.geometry.base import BaseGeometry

MIN_CIRCULARITY_AREA = 30.0  # px²; circularity of a handful of pixels is meaningless
SUFFIXES = (
    "area",
    "perimeter",
    "circularity",
    "solidity",
    "eccentricity",
    "major_axis_length",
    "minor_axis_length",
)


def ring_moments(coords):
    """Green's-theorem sums (A, m10, m01, m20, m02, m11) of one closed ring, signed by orientation."""
    x, y = coords[:-1, 0], coords[:-1, 1]
    x1, y1 = coords[1:, 0], coords[1:, 1]
    c = x * y1 - x1 * y
    return (
        c.sum() / 2,
        (c * (x + x1)).sum() / 6,
        (c * (y + y1)).sum() / 6,
        (c * (x * x + x * x1 + x1 * x1)).sum() / 12,
        (c * (y * y + y * y1 + y1 * y1)).sum() / 12,
        (c * (x * y1 + 2 * x * y + 2 * x1 * y1 + x1 * y)).sum() / 24,
    )


def axes(geom):
    """(major, minor, eccentricity) of the ellipse with the same second moments as `geom`."""
    import numpy as np
    from shapely import affinity
    from shapely.geometry.polygon import orient

    minx, miny, _, _ = geom.bounds
    # Shift to the origin: slide coordinates squared would lose float precision.
    geom = affinity.translate(geom, -minx, -miny)
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    total = np.zeros(6)
    for part in parts:
        part = orient(part, 1.0)  # exterior CCW, holes CW, so holes subtract
        for ring in (part.exterior, *part.interiors):
            total += ring_moments(np.asarray(ring.coords))
    area, m10, m01, m20, m02, m11 = total
    cx, cy = m10 / area, m01 / area
    mu20, mu02, mu11 = m20 / area - cx**2, m02 / area - cy**2, m11 / area - cx * cy
    half_diff = np.hypot((mu20 - mu02) / 2, mu11)
    l1 = (mu20 + mu02) / 2 + half_diff
    l2 = max((mu20 + mu02) / 2 - half_diff, 0.0)
    ecc = float(np.sqrt(1 - l2 / l1)) if l1 > 0 else 0.0
    return 4 * np.sqrt(l1), 4 * np.sqrt(l2), ecc


def shape_features(geoms: Sequence[BaseGeometry | None], index: pd.Index, prefix: str) -> pd.DataFrame:
    """Seven float64 columns `{prefix}_<feature>` indexed by `index`; NaN rows for None or empty geometries."""
    import numpy as np
    import pandas as pd
    import shapely

    out = np.full((len(geoms), len(SUFFIXES)), np.nan)
    valid = [i for i, g in enumerate(geoms) if g is not None and not g.is_empty]
    if valid:
        sel = np.array([geoms[i] for i in valid], dtype=object)
        area = shapely.area(sel)
        perimeter = shapely.length(sel)
        hull = shapely.area(shapely.convex_hull(sel))
        with np.errstate(divide="ignore", invalid="ignore"):
            circularity = np.where(area >= MIN_CIRCULARITY_AREA, 4 * np.pi * area / perimeter**2, np.nan)
            solidity = area / hull
        moments = np.array([axes(g) for g in sel])  # major, minor, eccentricity
        out[valid] = np.column_stack(
            [area, perimeter, circularity, solidity, moments[:, 2], moments[:, 0], moments[:, 1]]
        )
    return pd.DataFrame(out, index=index, columns=[f"{prefix}_{s}" for s in SUFFIXES])
