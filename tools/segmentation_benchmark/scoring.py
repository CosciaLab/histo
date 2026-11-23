"""Score predicted instance masks against ground truth by IoU matching.

Labels are integer instance masks (0 = background); ids need not be sequential or equal
between the two masks. Counts follow cellpose: a pair matches at IoU >= threshold, and
ap = tp / (tp + fp + fn) per threshold. Only overlapping pairs are built, so memory scales
with the number of objects, not with n_true * n_pred.
"""

from __future__ import annotations

import numpy as np

IOU_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
PRIMARY_THRESHOLD = 0.5


def score(true: np.ndarray, pred: np.ndarray) -> dict:
    """Object counts, F1 at 0.5, and average precision at each IoU threshold."""
    true = np.asarray(true)
    pred = np.asarray(pred)
    ids_t, area_t = np.unique(true[true > 0], return_counts=True)
    ids_p, area_p = np.unique(pred[pred > 0], return_counts=True)
    both = (true > 0) & (pred > 0)
    pairs, inter = np.unique(np.stack([true[both], pred[both]], axis=1), axis=0, return_counts=True)
    iou = inter / (
        area_t[np.searchsorted(ids_t, pairs[:, 0])] + area_p[np.searchsorted(ids_p, pairs[:, 1])] - inter
    )
    n_true, n_pred = len(ids_t), len(ids_p)
    order = np.argsort(-iou, kind="stable")
    pairs_sorted, iou_sorted = pairs[order].tolist(), iou[order].tolist()

    def counts(threshold: float) -> tuple[int, int, int]:
        # One-to-one, greedy by IoU: ties at exactly 0.5 match once.
        used_t, used_p, tp = set(), set(), 0
        for (t_id, p_id), value in zip(pairs_sorted, iou_sorted, strict=False):
            if value < threshold:
                break
            if t_id in used_t or p_id in used_p:
                continue
            used_t.add(t_id)
            used_p.add(p_id)
            tp += 1
        return tp, n_pred - tp, n_true - tp

    out = {"n_true": n_true, "n_pred": n_pred}
    for threshold in IOU_THRESHOLDS:
        tp, fp, fn = counts(threshold)
        if threshold == PRIMARY_THRESHOLD:
            out.update(tp=tp, fp=fp, fn=fn, f1=_ratio(2 * tp, 2 * tp + fp + fn))
        out[f"ap_{round(threshold * 100)}"] = _ratio(tp, tp + fp + fn)
    out["mean_ap"] = float(np.mean([out[f"ap_{round(t * 100)}"] for t in IOU_THRESHOLDS]))
    return out


def _ratio(num: int, den: int) -> float:
    """num / den as float, NaN when the denominator is 0 (nothing to score)."""
    return num / den if den else float("nan")
