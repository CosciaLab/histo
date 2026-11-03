#!/usr/bin/env python3
"""Segment one patch with sopa's Python API, on the image element a spec names.

sopa's CLI always reads the store attribute `cell_segmentation_image`; here the spec decides
('full' is that image, 'projected' is `<it>_projected`), so one store serves every spec.
The store is only read. The device comes from the process (`task.accelerator`), not the spec.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
import tempfile
from pathlib import Path

SEGMENTATION_ATTR = "cell_segmentation_image"  # sopa's SopaAttrs.CELL_SEGMENTATION
METHOD_BUILDERS = {"cellpose": "cellpose_patch", "instanseg": "instanseg_patch"}
# The builders name the device choice differently.
DEVICE_ARGUMENT = {"cellpose": "gpu", "instanseg": "device"}
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


def require_image(key: str, images, image: str) -> None:
    """Fail naming the cause when the spec's image element is not in the store."""
    if key in images:
        return
    if image == "projected":
        # WRITE_SEGMENTATIONS drops it; a -resume that reruns only segmentation then lacks it.
        raise ValueError(
            f"image '{key}' is not in the store: projection removed by an earlier run; "
            "rerun without -resume, or set keep_projection"
        )
    raise ValueError(f"image '{key}' is not in the store; images: {sorted(images)}")


def _check_method(method: str) -> None:
    if method not in METHOD_BUILDERS:
        raise ValueError(f"unknown segmentation method '{method}'; expected one of {sorted(METHOD_BUILDERS)}")


def extra_kwargs(spec: dict) -> dict:
    """`method_kwargs_extra` ({method}_kwargs): a Python dict literal, read as sopa's 1.x CLI did."""
    text = spec.get("method_kwargs_extra")
    if not text:
        return {}
    param = f"{spec['method']}_kwargs"
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"{param} is not a Python literal: {text!r} ({e})") from e
    if not isinstance(value, dict):
        raise ValueError(f"{param} must be a Python dict such as \"{{'niter': 10}}\", got {text!r}")
    return value


def method_arguments(spec: dict) -> dict:
    """Keyword arguments for sopa's method builder: CLI defaults, the spec's method_kwargs, then its extras."""
    _check_method(spec["method"])
    explicit = spec.get("method_kwargs") or {}
    extra = extra_kwargs(spec)
    # Set by dedicated parameters, or by --device; an extra must not silently override them.
    taken = set(explicit) | {"channels", DEVICE_ARGUMENT[spec["method"]]}
    clash = sorted(set(extra) & taken)
    if clash:
        param = f"{spec['method']}_kwargs"
        raise ValueError(
            f"{param} key {', '.join(map(repr, clash))} collides with a dedicated parameter. Remove it from {param}."
        )
    kwargs = {**METHOD_DEFAULTS[spec["method"]], **explicit, **extra}
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
    kwargs = method_arguments(spec)  # first: a bad {method}_kwargs fails before the store is read
    sdata = read_zarr_standardized(args.sdata)
    key = image_key_for(sdata.attrs, spec["image"])
    require_image(key, sdata.images, spec["image"])

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
