"""Normalise the benchmark datasets into one crop layout.

Writes `crops/<dataset>/<crop>/{image,cells,nuclei}.tif` (image C,Y,X as stored; labels
uint32; a label file is absent when the dataset has no such mask) and `crops.csv`. Every
run rewrites everything it finds, so re-running after a download only adds crops.

Findings from inspecting the data (Cross-platform = Aleynick et al. 2023, Sci Data):
- Cross-platform ROIs are all FREEHAND polygons; no other type occurs. Neighbouring cells
  share boundary pixels, so 5-15% of foreground is covered twice; the later ROI wins and the
  share is reported. The dataset's own *_Mask_Png.png draws cells with a 1-px gap, so it
  matches our fill in the interior only (see the report for agreement numbers).
- Vectra crop TIFFs are (8, 400, 400) float32 with no channel names; the xlsx lists markers by
  colour in an order that is not the file order. DAPI is the channel that equals the crop's
  *_Dapi_Png.png (index 5 on all of P01); other channels are named ch<i>. Pixel size 0.5 um.
- CODEX crop TIFFs are (T, 4, 400, 400) uint16, T cycles x 4 channels; flattening t*4+c gives
  the "Channel Name" order of the xlsx Markers sheet. We keep DAPI1 (index 0) and the real
  markers and drop Blank/Empty channels and the repeat DAPI cycles, so "every non-DNA channel"
  holds. Pixel size 0.3774 um.
- Tonsil (Zenodo 22107836): (7, 100, 100) uint16, DAPI is index 6 on all 10 crops (checked by
  `tonsil_nuclear_channel`); nuclei ids are a subset of cell ids. Pixel size unknown.
- TissueNet is not read here yet; its reader is added once the zip is available.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
from skimage.draw import polygon

PIXEL_SIZE_UM = {"Vectra": 0.5, "CODEX": 0.3774}  # paper Table 2
POLYGON_TYPES = ("POLYGON", "FREEHAND", "TRACED")
DAPI_MIN_CORR = 0.9
COLUMNS = [
    "dataset", "crop", "platform", "tissue", "pixel_size_um", "channels", "nuclear",
    "height", "width", "montage", "n_cells", "n_nuclei",
]  # fmt: skip


def rois_to_labels(rois: list, shape: tuple[int, int]) -> tuple[np.ndarray, float]:
    """Instance labels 1..N in ROI order, and the share of foreground covered by 2+ ROIs."""
    labels = np.zeros(shape, np.uint32)
    covered = np.zeros(shape, np.uint8)
    for i, roi in enumerate(rois, 1):
        if roi.roitype.name not in POLYGON_TYPES:
            raise ValueError(f"ROI {i} has unsupported type {roi.roitype.name}")
        xy = roi.coordinates()
        rr, cc = polygon(xy[:, 1], xy[:, 0], shape)
        labels[rr, cc] = i  # the later ROI wins an overlap
        covered[rr, cc] = np.minimum(covered[rr, cc] + 1, 2)
    foreground = (covered > 0).sum()
    return labels, float((covered > 1).sum() / foreground) if foreground else 0.0


def tonsil_nuclear_channel(image: np.ndarray, nuclei: np.ndarray) -> int:
    """The channel most enriched inside nuclei (mean inside / mean outside)."""
    inside = nuclei > 0
    ratio = [ch[inside].mean() / max(ch[~inside].mean(), 1e-9) for ch in image]
    return int(np.argmax(ratio))


def _key(name: str) -> str:
    """File and xlsx crop names differ in brackets and dots; compare alphanumerics only."""
    return re.sub(r"[^A-Za-z0-9]", "", name).lower()


def _crop_name(folder: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", folder.strip()).strip("_")


def _one(folder: Path, pattern: str, skipped: list) -> Path | None:
    found = sorted(folder.glob(pattern))
    if len(found) > 1:
        skipped.append((folder.name, f"{len(found)} files match {pattern}"))
        return None
    return found[0] if found else None


def _read_rois(zip_path: Path | None, shape: tuple[int, int]) -> tuple[np.ndarray | None, float]:
    import roifile

    if zip_path is None:
        return None, 0.0
    return rois_to_labels(roifile.roiread(zip_path), shape)


def _panel_tables(xlsx: Path) -> tuple[dict, dict]:
    """(crop key -> tissue, CODEX sample prefix -> channel names in file order)."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    tissue, codex = {}, {}
    for sheet in ("Vectra", "Codex"):
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            if row[0] and row[1] and "Markers" not in str(row[0]):
                tissue[_key(str(row[0]))] = str(row[1]).strip()
    prefix = None
    for row in wb["Codex"].iter_rows(min_row=2, values_only=True):
        if row[0] and str(row[0]).endswith(" Markers"):
            prefix = str(row[0]).removesuffix(" Markers")
            codex[prefix] = []
        if prefix and isinstance(row[1], int) and row[2]:
            codex[prefix].append(str(row[2]).strip())
    return tissue, codex


def _codex_channels(img: np.ndarray, folder: str, panels: dict, skipped: list):
    """Flatten (T, 4, Y, X); keep DAPI1 and the real markers. None when names do not fit."""
    img = img.reshape(-1, *img.shape[-2:])
    names = next((v for k, v in panels.items() if folder.lower().startswith(k.lower())), None)
    if names is None or len(names) != len(img):
        skipped.append(
            (folder, f"panel names {None if names is None else len(names)} != {len(img)} channels")
        )
        return None
    keep = [i for i, n in enumerate(names) if n == "DAPI1" or not re.fullmatch(r"Blank|Empty|DAPI\d", n)]
    return img[keep], [names[i] for i in keep], 0


def _vectra_nuclear(img: np.ndarray, dapi_png: Path | None) -> int | None:
    """The channel that equals the dataset's own DAPI render; None if none correlates."""
    if dapi_png is None:
        return None
    from PIL import Image

    try:  # PIL sniffs content: some *_Png.png files are really TIFFs
        ref = np.asarray(Image.open(dapi_png), dtype=float)
    except OSError:  # a file still downloading
        return None
    ref = ref if ref.ndim == 2 else ref[..., :3].mean(-1)
    corr = [np.corrcoef(ch.ravel(), ref.ravel())[0, 1] for ch in img]
    best = int(np.nanargmax(corr))
    return best if corr[best] >= DAPI_MIN_CORR else None


def read_crossplatform(root: Path, skipped: list | None = None):
    """Yield (row, image, cells, nuclei) per Vectra/CODEX crop; skips are appended to `skipped`."""
    root = Path(root)
    skipped = skipped if skipped is not None else []
    xlsx = root / "Annotation Panel Table.xlsx"
    tissues, panels = _panel_tables(xlsx)
    folders = sorted((p for p in (root / "Vectra").glob("*/*") if p.is_dir()), key=lambda p: p.name) + sorted(
        (p for p in (root / "CODEX").glob("*") if p.is_dir()), key=lambda p: p.name
    )
    for folder in folders:
        platform = "Vectra" if folder.parent.parent.name == "Vectra" else "CODEX"
        tif = _one(folder, "*-Crop_Tif*.tif", skipped)  # also matches -Crop_Tiff.tif
        if tif is None:
            skipped.append((folder.name, "no crop TIFF"))
            continue
        cell_zip = _one(folder, "*Cell_Mask_Roi_Zip*.zip", skipped)
        dapi_zip = _one(folder, "*Dapi_Mask_Roi_Zip*.zip", skipped)  # also Roi_Zip-1.zip
        if cell_zip is None and dapi_zip is None:
            skipped.append((folder.name, "no cell or nuclei ROIs"))
            continue
        img = tifffile.imread(tif)
        if platform == "CODEX":
            out = _codex_channels(img, folder.name, panels, skipped)
            if out is None:
                continue
            img, names, nuclear = out
        else:
            nuclear = _vectra_nuclear(img, _one(folder, "*Dapi_Png.png", skipped))
            if nuclear is None:
                skipped.append((folder.name, "DAPI channel not identified (no *_Dapi_Png.png match)"))
                continue
            names = [f"ch{i}" for i in range(len(img))]
            names[nuclear] = "DAPI"
        shape = img.shape[-2:]
        cells, overlap_c = _read_rois(cell_zip, shape)
        nuclei, overlap_n = _read_rois(dapi_zip, shape)
        row = {
            "dataset": "crossplatform", "crop": _crop_name(folder.name), "platform": platform,
            "tissue": tissues.get(_key(folder.name), "unknown"),
            "pixel_size_um": PIXEL_SIZE_UM[platform], "channels": "|".join(names),
            "nuclear": nuclear, "height": shape[0], "width": shape[1],
            "n_cells": 0 if cells is None else int(cells.max()),
            "n_nuclei": 0 if nuclei is None else int(nuclei.max()),
            "overlap_cells": overlap_c, "overlap_nuclei": overlap_n,
        }  # fmt: skip
        if row["tissue"] == "unknown":
            skipped.append((folder.name, "tissue not found in xlsx (kept as unknown)"))
        yield row, img, cells, nuclei


def read_tonsil(root: Path):
    """Yield (row, image, cells, nuclei) per Zenodo tonsil crop."""
    names = ["CD21", "CD23", "CD20", "CD4", "CK", "CD8", "DAPI"]
    for tif in sorted(Path(root).glob("*.tif")):
        if "_GT_" in tif.name:
            continue
        img = tifffile.imread(tif)
        cells = tifffile.imread(tif.with_name(tif.stem + "_GT_cells.tif")).astype(np.uint32)
        nuclei = tifffile.imread(tif.with_name(tif.stem + "_GT_nuclei.tif")).astype(np.uint32)
        nuclear = tonsil_nuclear_channel(img, nuclei)
        assert nuclear == 6, f"{tif.name}: DAPI expected at 6, found {nuclear}"
        row = {
            "dataset": "tonsil", "crop": tif.stem, "platform": "unknown", "tissue": "tonsil",
            "pixel_size_um": np.nan, "channels": "|".join(names), "nuclear": nuclear,
            "height": img.shape[1], "width": img.shape[2],
            "n_cells": len(np.unique(cells)) - 1, "n_nuclei": len(np.unique(nuclei)) - 1,
            "overlap_cells": 0.0, "overlap_nuclei": 0.0,
        }  # fmt: skip
        yield row, img, cells, nuclei


def _mark_montage(rows: list[dict]) -> None:
    """First crop by name per Cross-platform platform (with cell masks) and first two tonsil."""
    for r in rows:
        r["montage"] = False
    ordered = sorted(rows, key=lambda r: (r["dataset"], r["crop"]))
    seen = Counter()
    for r in ordered:
        group, limit = (r["platform"], 1) if r["dataset"] == "crossplatform" else (r["dataset"], 2)
        if r["n_cells"] and seen[group] < limit:
            r["montage"] = True
            seen[group] += 1


def prepare(raw: Path, out: Path) -> tuple[pd.DataFrame, list]:
    raw, out = Path(raw), Path(out)
    skipped: list = []
    readers = []
    if (raw / "crossplatform").is_dir():
        readers.append(read_crossplatform(raw / "crossplatform", skipped))
    if (raw / "tonsil").is_dir():
        readers.append(read_tonsil(raw / "tonsil"))
    rows = []
    for reader in readers:
        for row, image, cells, nuclei in reader:
            folder = out / "crops" / row["dataset"] / row["crop"]
            folder.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(folder / "image.tif", image)
            for name, labels in (("cells", cells), ("nuclei", nuclei)):
                if labels is not None:
                    tifffile.imwrite(folder / f"{name}.tif", labels.astype(np.uint32))
                else:
                    (folder / f"{name}.tif").unlink(missing_ok=True)
            rows.append(row)
    _mark_montage(rows)
    table = pd.DataFrame(rows)
    table[COLUMNS].to_csv(out / "crops.csv", index=False)
    return table, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the benchmark crops and crops.csv.")
    parser.add_argument("--raw", type=Path, required=True, help="folder with tonsil/, crossplatform/")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    table, skipped = prepare(args.raw, args.out)
    for folder, why in skipped:
        print(f"skipped {folder}: {why}", file=sys.stderr)
    print(
        table.groupby("dataset").agg(
            crops=("crop", "size"), cells=("n_cells", "sum"), nuclei=("n_nuclei", "sum"),
            nuclei_crops=("n_nuclei", lambda s: int((s > 0).sum())),
            max_overlap_cells=("overlap_cells", "max"), max_overlap_nuclei=("overlap_nuclei", "max"),
        ).to_string()
    )  # fmt: skip
    print(f"montage crops: {table.loc[table['montage'], ['dataset', 'crop']].values.tolist()}")


if __name__ == "__main__":
    main()
