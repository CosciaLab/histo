"""Normalise the benchmark datasets into one crop layout.

Writes `crops/<dataset>/<crop>/{image,cells,nuclei}.tif` (image C,Y,X as stored; labels
uint32; a label file is absent when the dataset has no such mask) and `crops.csv`. Every
run rewrites everything it finds, so re-running after a download only adds crops.

Findings from inspecting the data (Cross-platform = Aleynick et al. 2023, Sci Data):
- Cross-platform ROIs are all FREEHAND polygons; no other type occurs. Neighbouring cells
  share boundary pixels, so 5-15% of foreground is covered twice; the later ROI wins and the
  share is reported. The dataset's own *_Mask_Png.png draws cells with a 1-px gap, so it
  matches our fill in the interior only (see the report for agreement numbers).
- Vectra crop TIFFs are (8, 400, 400) float32 ImageJ hyperstacks; the inForm channel names
  (marker, Opal dye, DAPI or Hoechst, Autofluorescence) are in the ImageJ Info field as
  `Name #k = ...`. DAPI is found independently: the channel best correlated with the pure-blue
  part (B - max(R, G)) of the crop's own *_Cell_Png.png composite; *_Dapi_Png.png is only a
  cross-check. A crop whose DAPI channel is not named DAPI/Hoechst is skipped. Without names,
  channels are ch<i>. P05's CD40L is poor quality per the xlsx; kept. 0.5 um/px.
- CODEX crop TIFFs are (T, 4, 400, 400) uint16, T cycles x 4 channels; flattening t*4+c gives
  the "Channel Name" order of the xlsx Markers sheet. We keep DAPI1 (index 0) and the real
  markers and drop Blank/Empty channels and the repeat DAPI cycles, so "every non-DNA channel"
  holds (accepted: a user's marker sheet would do the same). Pixel size 0.3774 um.
- Tonsil (Zenodo 22107836): (7, 100, 100) uint16, DAPI is index 6 on all 10 crops (checked by
  `tonsil_nuclear_channel`); nuclei ids are a subset of cell ids. Pixel size unknown.
- TissueNet 1.1 test npz (modified Apache, non-commercial): X (N,256,256,2) = [nuclear, whole
  cell], y (N,256,256,2) = [whole cell, nuclear]; `meta` has 4 header rows (header text
  repeated) before N data rows, checked to be 1:1 with X. platform = experiment folder name,
  tissue = specimen, 0.5 um/px. Only the test split is read.
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
TISSUENET_TEST = "tissuenet_v1.1_test.npz"
TISSUENET_MONTAGE_MIN_CELLS = 20
DAPI_MIN_BLUE_CORR = 0.5
DAPI_MIN_MARGIN = 0.1
DNA_NAMES = ("dapi", "hoechst")
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


def _load_png(path: Path | None) -> np.ndarray | None:
    from PIL import Image

    if path is None:
        return None
    try:  # PIL sniffs content: some *_Png.png files are really TIFFs
        return np.asarray(Image.open(path))
    except OSError:  # a file still downloading
        return None


def _correlations(image: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Pearson r of each channel with `ref`, at ref's resolution."""
    from PIL import Image

    out = []
    for ch in image:
        if ch.shape != ref.shape:
            ch = np.asarray(Image.fromarray(ch.astype(np.float32)).resize(ref.shape[::-1]))
        out.append(np.corrcoef(ch.ravel(), ref.ravel())[0, 1])
    return np.nan_to_num(np.array(out), nan=-1.0)


def dapi_from_composite(image: np.ndarray, rgb: np.ndarray) -> tuple[int | None, str]:
    """DAPI is blue in every Vectra panel: pick the channel best matching the pure-blue part."""
    rgb = rgb[..., :3].astype(float)
    blue = np.clip(rgb[..., 2] - np.maximum(rgb[..., 0], rgb[..., 1]), 0, None)  # cyan/white are not DAPI
    corr = _correlations(image, blue)
    order = np.argsort(-corr)
    if corr[order[0]] < DAPI_MIN_BLUE_CORR:
        return None, f"best blue correlation {corr[order[0]]:.2f} < {DAPI_MIN_BLUE_CORR}"
    if corr[order[0]] - corr[order[1]] < DAPI_MIN_MARGIN:
        return (
            None,
            f"top two blue correlations within {DAPI_MIN_MARGIN} ({corr[order[0]]:.2f}, {corr[order[1]]:.2f})",
        )
    return int(order[0]), ""


def _vectra_nuclear(img: np.ndarray, folder: Path, skipped: list) -> tuple[int | None, str]:
    """(DAPI index, check). The composite decides; the DAPI render, when present, only checks."""
    dapi = _load_png(_one(folder, "*Dapi_Png.png", skipped))
    by_dapi, corr = None, None
    if dapi is not None:
        dapi = dapi if dapi.ndim == 2 else dapi[..., :3].mean(-1)
        corr = _correlations(img, dapi.astype(float))
        by_dapi = int(np.argmax(corr)) if corr.max() >= DAPI_MIN_CORR else None
    composite = _load_png(_one(folder, "*-Crop_Cell_Png.png", skipped))
    if composite is None or composite.ndim != 3:
        if by_dapi is None:
            skipped.append((folder.name, "DAPI not identified: no usable composite or DAPI PNG"))
            return None, "none"
        return by_dapi, "dapi-png only"
    index, why = dapi_from_composite(img, composite)
    if index is None:
        skipped.append((folder.name, f"DAPI not identified from composite: {why}"))
        return None, "none"
    if by_dapi is None:
        return index, "composite only"
    if by_dapi != index:  # trust neither
        skipped.append(
            (
                folder.name,
                f"DAPI methods disagree: composite ch{index} (DAPI-PNG r={corr[index]:.2f}), "
                f"DAPI PNG ch{by_dapi} (r={corr[by_dapi]:.2f})",
            )
        )
        return None, "disagree"
    return index, "agree"


def vectra_channel_names(tif: Path) -> list[str] | None:
    """inForm channel names from the ImageJ Info field, or None when absent or not 1..N."""
    with tifffile.TiffFile(tif) as t:
        info = (t.imagej_metadata or {}).get("Info", "")
    found = {int(k): v.strip() for k, v in re.findall(r"^Name #(\d+) = (.*)$", info, flags=re.M)}
    if not found or sorted(found) != list(range(1, len(found) + 1)):
        return None
    return [found[k] for k in sorted(found)]


def is_dna_name(name: str) -> bool:
    return name.strip().lower().startswith(DNA_NAMES)


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
            nuclear, check = _vectra_nuclear(img, folder, skipped)
            if nuclear is None:
                continue
            names = vectra_channel_names(tif)
            if names is None or len(names) != len(img):
                names = [f"ch{i}" for i in range(len(img))]
                names[nuclear] = "DAPI"
            elif not is_dna_name(names[nuclear]):
                skipped.append((folder.name, f"DAPI found at ch{nuclear}, which is named {names[nuclear]!r}"))
                continue
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
            "dapi_check": check if platform == "Vectra" else "n/a",
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
            "overlap_cells": 0.0, "overlap_nuclei": 0.0, "dapi_check": "n/a",
        }  # fmt: skip
        yield row, img, cells, nuclei


def read_tissuenet(npz: Path):
    """Yield (row, image, cells, nuclei) per tile of a TissueNet test npz."""
    data = np.load(npz, allow_pickle=True)  # meta is an object array
    x, y, meta = data["X"], data["y"], data["meta"]
    is_header = meta[:, 0] == "filename"
    meta = meta[~is_header]
    if len(meta) != len(x) or len(y) != len(x) or x.shape[-1] != 2 or y.shape[-1] != 2:
        raise ValueError(
            f"TissueNet meta rows {len(meta)} (after {is_header.sum()} headers) != {len(x)} tiles"
        )
    for i, (m, tile, lab) in enumerate(zip(meta, x, y, strict=True)):
        image = np.moveaxis(tile, -1, 0).astype(np.float32)  # [nuclear, whole cell]
        cells, nuclei = lab[..., 0].astype(np.uint32), lab[..., 1].astype(np.uint32)
        row = {
            "dataset": "tissuenet", "crop": f"{i:04d}", "platform": Path(str(m[1])).name,
            "tissue": str(m[5]), "pixel_size_um": float(m[2]), "channels": "nuclear|membrane",
            "nuclear": 0, "height": image.shape[1], "width": image.shape[2],
            "n_cells": len(np.unique(cells)) - 1, "n_nuclei": len(np.unique(nuclei)) - 1,
            "overlap_cells": 0.0, "overlap_nuclei": 0.0, "dapi_check": "n/a",
        }  # fmt: skip
        yield row, image, cells, nuclei


def _mark_montage(rows: list[dict]) -> None:
    """First crop by name per Cross-platform platform (with cell masks), first two tonsil, first TissueNet tile with 20+ cells."""
    for r in rows:
        r["montage"] = False
    ordered = sorted(rows, key=lambda r: (r["dataset"], r["crop"]))
    seen = Counter()
    for r in ordered:
        group, limit = (r["platform"], 1) if r["dataset"] == "crossplatform" else (r["dataset"], 2)
        need = TISSUENET_MONTAGE_MIN_CELLS if r["dataset"] == "tissuenet" else 1
        limit = 1 if r["dataset"] == "tissuenet" else limit
        if r["n_cells"] >= need and seen[group] < limit:
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
    if (raw / "tissuenet" / TISSUENET_TEST).is_file():
        readers.append(read_tissuenet(raw / "tissuenet" / TISSUENET_TEST))
    rows = []
    for reader in readers:
        for row, image, cells, nuclei in reader:
            folder = out / "crops" / row["dataset"] / row["crop"]
            folder.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(folder / "image.tif", image, compression="zlib")
            for name, labels in (("cells", cells), ("nuclei", nuclei)):
                if labels is not None:
                    tifffile.imwrite(folder / f"{name}.tif", labels.astype(np.uint32), compression="zlib")
                else:
                    (folder / f"{name}.tif").unlink(missing_ok=True)
            rows.append(row)
    _mark_montage(rows)
    table = pd.DataFrame(rows)
    table[COLUMNS].to_csv(out / "crops.csv", index=False)
    return table, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the benchmark crops and crops.csv.")
    parser.add_argument(
        "--raw", type=Path, required=True, help="folder with tonsil/, crossplatform/, tissuenet/"
    )
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
    print(f"Vectra DAPI check: {dict(table.loc[table['platform'] == 'Vectra', 'dapi_check'].value_counts())}")
    print(f"montage crops: {table.loc[table['montage'], ['dataset', 'crop']].values.tolist()}")


if __name__ == "__main__":
    main()
