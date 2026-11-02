#!/usr/bin/env python3
"""Segment one patch with sopa's Python API, on the image element a spec names.

sopa's CLI always reads the store attribute `cell_segmentation_image`; here the spec decides
('full' is that image, 'projected' is `<it>_projected`), so one store serves every spec.
The store is only read. The device comes from the process (`task.accelerator`), not the spec.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

SEGMENTATION_ATTR = "cell_segmentation_image"  # sopa's SopaAttrs.CELL_SEGMENTATION
METHOD_BUILDERS = {"cellpose": "cellpose_patch", "instanseg": "instanseg_patch"}
# Defaults copied from sopa 2.2.12 cli/segmentation.py, so unset params segment as the CLI does.
METHOD_DEFAULTS = {
    # cli/segmentation.py:18-27 (diameter has no default; gpu is set by --device)
    "cellpose": {
        "flow_threshold": 2,
        "cellprob_threshold": -6,
        "model_type": "cyto3",
        "pretrained_model": None,
        "gpu": False,
    },
    # cli/segmentation.py:148-158 (device is set by --device)
    "instanseg": {
        "model_type": "fluorescence_nuclei_and_cells",
        "pixel_size": None,
        "target": "cells",
        "device": None,
    },
}
SEGMENTATION_DEFAULTS = {
    # cli/segmentation.py:28-39 (cellpose) and :160-172 (instanseg)
    "cellpose": {"min_area": 0, "clip_limit": 0.2, "clahe_kernel_size": None, "gaussian_sigma": 1},
    "instanseg": {"min_area": 0, "clip_limit": 0, "clahe_kernel_size": None, "gaussian_sigma": 0},
}


def image_key_for(attrs: dict, image: str) -> str:
    """Image element a spec reads: 'full' is the store's segmentation image, 'projected' its projection."""
    if SEGMENTATION_ATTR not in attrs:
        raise ValueError(f"store attribute '{SEGMENTATION_ATTR}' is missing; was the store prepared by sopa?")
    base = attrs[SEGMENTATION_ATTR]
    if image == "full":
        return base
    if image == "projected":
        return f"{base}_projected"
    raise ValueError(f"spec image must be 'full' or 'projected', got '{image}'")


def _check_method(method: str) -> None:
    if method not in METHOD_BUILDERS:
        raise ValueError(f"unknown segmentation method '{method}'; expected one of {sorted(METHOD_BUILDERS)}")


def method_arguments(spec: dict) -> dict:
    """Keyword arguments for sopa's method builder: CLI defaults, then the spec's method_kwargs."""
    _check_method(spec["method"])
    kwargs = {**METHOD_DEFAULTS[spec["method"]], **(spec.get("method_kwargs") or {})}
    if spec.get("channels") is not None:
        kwargs["channels"] = spec["channels"]
    return kwargs


def segmentation_arguments(spec: dict) -> dict:
    """StainingSegmentation keyword arguments: per-method CLI defaults, then the spec's segmentation_kwargs."""
    _check_method(spec["method"])
    return {**SEGMENTATION_DEFAULTS[spec["method"]], **(spec.get("segmentation_kwargs") or {})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdata", required=True)
    parser.add_argument("--spec", required=True, help="JSON file with one segmentation spec")
    parser.add_argument("--patch-index", type=int, required=True)
    parser.add_argument("--output", required=True, help="parquet file to write")
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    args = parser.parse_args()

    from sopa.io.standardize import read_zarr_standardized
    from sopa.segmentation import StainingSegmentation, methods

    spec = json.loads(Path(args.spec).read_text())
    sdata = read_zarr_standardized(args.sdata)
    key = image_key_for(sdata.attrs, spec["image"])

    kwargs = method_arguments(spec)
    # The builders name the same choice differently: Cellpose `gpu`, InstanSeg `device`.
    if spec["method"] == "cellpose":
        kwargs["gpu"] = args.device == "cuda"
    else:
        kwargs["device"] = args.device
    method = getattr(methods, METHOD_BUILDERS[spec["method"]])(**kwargs)

    segmentation = StainingSegmentation(
        sdata, method, spec.get("channels"), image_key=key, **segmentation_arguments(spec)
    )
    print(f"[segment_patch] {spec['name']} patch {args.patch_index} on image '{key}', device {args.device}")
    with tempfile.TemporaryDirectory() as tmp:
        segmentation.write_patch_cells(tmp, args.patch_index)
        shutil.move(str(Path(tmp) / f"{args.patch_index}.parquet"), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
