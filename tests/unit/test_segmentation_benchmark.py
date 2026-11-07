"""Unit tests for the segmentation benchmark tools."""

from __future__ import annotations

import numpy as np
from segmentation_benchmark.scoring import score


def square(labels, value, y, x, size=10):
    labels[y : y + size, x : x + size] = value


def test_identical_masks_score_one():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0)
    square(t, 2, 20, 20)
    s = score(t, t.copy())
    assert (s["tp"], s["fp"], s["fn"], s["f1"], s["mean_ap"]) == (2, 0, 0, 1.0, 1.0)


def test_shifted_object_counts_by_iou():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0)
    p = np.zeros_like(t)
    square(p, 7, 0, 2)  # IoU 80/120 = 0.667, labels need not match
    s = score(t, p)
    assert s["tp"] == 1 and s["ap_60"] == 1.0 and s["ap_70"] == 0.0


def test_one_side_empty_is_zero_both_empty_is_nan():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0)
    assert score(t, np.zeros_like(t))["f1"] == 0.0
    assert np.isnan(score(np.zeros_like(t), np.zeros_like(t))["f1"])


def test_split_cell_is_one_fn_three_fp():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0, 20)  # 400 px
    p = np.zeros_like(t)
    p[0:20, 0:7] = 1
    p[0:20, 7:14] = 2
    p[0:20, 14:20] = 3  # IoU 0.35, 0.35, 0.30
    s = score(t, p)
    assert (s["tp"], s["fp"], s["fn"]) == (0, 3, 1)


def test_exact_half_iou_matches_once():
    t = np.zeros((50, 50), int)
    square(t, 1, 0, 0, 20)  # 400 px
    p = np.zeros_like(t)
    p[0:20, 0:10] = 1
    p[0:20, 10:20] = 2  # each IoU exactly 0.5
    s = score(t, p)
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 0)
