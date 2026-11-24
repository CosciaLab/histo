#!/usr/bin/env python3
"""Run one benchmark setting (one SLURM array task) over its crops and write results/N.csv.

Cells on raw datasets: project -> sopa preprocessing -> Cellpose on [cell, nuclear].
TissueNet: rescale only. Nuclei: the nuclear plane alone. A target is scored on crops that
have its mask file; an all-zero mask is a real "no objects" crop.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from segmentation_benchmark.preprocess import cell_channels, pad_to, project, sopa_preprocess, unpad  # noqa: E402
from segmentation_benchmark.scoring import score  # noqa: E402
from segmentation_benchmark.settings import GRIDS  # noqa: E402

SCOPES = {
    "raw": ["crossplatform", "tonsil"],
    "tissuenet": ["tissuenet"],
    "all": ["crossplatform", "tonsil", "tissuenet"],
}
_models: dict = {}


def segment(image: np.ndarray, _channels: list[str], setting: pd.Series, gpu: bool) -> np.ndarray:
    """Cellpose-SAM, loaded once per task; sopa's callable reloads the model per call, this mirrors its eval."""
    if gpu not in _models:
        import warnings

        from sopa.segmentation.methods._cellpose import load_cellpose_model

        warnings.filterwarnings("ignore", message="You are using `torch.load` with `weights_only=False`")
        _models[gpu] = load_cellpose_model(
            model_type="cyto3", pretrained_model="cpsam_v2", gpu=gpu, cellpose_model_kwargs=None
        )
    mask, *_ = _models[gpu].eval(
        image,
        diameter=30,
        channels=None,  # cellpose 4 ignores channel names, as in sopa
        flow_threshold=float(setting["flow_threshold"]),
        cellprob_threshold=float(setting["cellprob_threshold"]),
    )
    return np.asarray(mask)


def prepare_input(image: np.ndarray, crop: pd.Series, setting: pd.Series) -> tuple[np.ndarray, list[str]]:
    """Preprocessed (C, Y, X) and the channel names to segment."""
    nuclear = int(crop["nuclear"])
    if crop["dataset"] == "tissuenet":  # its projection factors do not vary
        projected = project(image, nuclear, "max", 1, 0)
    else:
        names = str(crop["channels"]).split("|")
        projected = project(
            image,
            nuclear,
            setting["projection_method"],
            setting["low_percentile"],
            setting["projection_sigma"],
            cell_idx=cell_channels(names, nuclear, setting["cell_channels"]),
        )
    if setting["target"] == "nuclei":
        projected, channels = projected[1:2], ["nuclear"]
    else:
        channels = ["cell", "nuclear"]
    return sopa_preprocess(projected, setting["gaussian_sigma"], setting["clip_limit"]), channels


def run(
    data: Path,
    index: int,
    out: Path,
    gpu: bool = False,
    limit_crops: int | None = None,
    dataset: str | None = None,
    grid: str = "round1",
) -> None:
    partial = bool(limit_crops or dataset)  # partial runs must never look complete
    final = out / "results" / (f"{index}.partial.csv" if partial else f"{index}.csv")
    if not partial and final.exists():
        print(f"setting {index}: {final} exists, skipping", flush=True)
        return
    setting = GRIDS[grid]().set_index("index").loc[index]
    crops = pd.read_csv(data / "crops.csv", dtype={"crop": str})
    crops = crops[crops["dataset"].isin(SCOPES[setting["scope"]])]
    if dataset:
        crops = crops[crops["dataset"] == dataset]
    mask_name = f"{setting['target']}.tif"
    has_mask = [
        (data / "crops" / d / c / mask_name).exists()
        for d, c in zip(crops["dataset"], crops["crop"], strict=False)
    ]
    crops = crops[has_mask]
    if limit_crops:
        crops = crops.head(limit_crops)
    if crops.empty:
        raise SystemExit(
            f"setting {index}: no crops for scope {setting['scope']!r} and target {setting['target']!r} in {data}"
        )

    rows, start = [], time.time()
    for _, crop in crops.iterrows():
        t0 = time.time()
        folder = data / "crops" / crop["dataset"] / crop["crop"]
        image, truth = tifffile.imread(folder / "image.tif"), tifffile.imread(folder / mask_name)
        prepared, channels = prepare_input(image, crop, setting)
        padded, shape = pad_to(prepared)
        labels = unpad(segment(padded, channels, setting, gpu), shape)
        seconds = time.time() - t0
        s = score(truth, labels)
        rows.append(
            {
                "index": index,
                "target": setting["target"],
                "dataset": crop["dataset"],
                "crop": crop["crop"],
                "platform": crop["platform"],
                **s,
                "seconds": round(seconds, 2),
            }
        )
        if crop["montage"]:
            label_dir = out / "labels" / str(index)
            label_dir.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(label_dir / f"{crop['dataset']}__{crop['crop']}.tif", labels.astype(np.uint32))
        print(f"{crop['dataset']} {crop['crop']} f1={s['f1']:.3f} {seconds:.1f}s", flush=True)

    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")
    pd.DataFrame(rows).to_csv(tmp, index=False)
    tmp.replace(final)  # atomic on POSIX
    mean_f1 = np.nanmean([r["f1"] for r in rows]) if rows else float("nan")
    print(
        f"setting {index}: {len(rows)} crops, mean f1={mean_f1:.3f}, {time.time() - start:.0f}s", flush=True
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--setting-index", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--limit-crops", type=int)
    p.add_argument("--dataset", choices=["crossplatform", "tonsil", "tissuenet"])
    p.add_argument("--grid", choices=GRIDS, default="round1")
    a = p.parse_args()
    run(a.data, a.setting_index, a.out, a.gpu, a.limit_crops, a.dataset, a.grid)


if __name__ == "__main__":
    main()
