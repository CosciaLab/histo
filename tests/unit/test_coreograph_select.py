"""Tests for scoring and choosing the Coreograph downsample factor in coreograph_select.py."""

import csv
import json
import math

import matplotlib.pyplot as plt
import numpy as np
import pytest
from coreograph_select import choose, main, score, warning


def m(k, n, ce, de, cv):
    return {
        "k": k, "n_cores": n, "count_error": ce, "diam_error": de, "size_cv": cv,
        "um_per_px": 0.65 * 2**k, "diam_mm": None if de is None else 1.5, "crop_ratio": None,
        "core_px_at_k": 1500 / 0.65 / 2**k,
    }  # fmt: skip


def write_sweep(tmp_path, metrics):
    jsons, pngs = [], []
    for d in metrics:
        j = tmp_path / f"s_k{d['k']}_metrics.json"
        j.write_text(json.dumps(d))
        p = tmp_path / f"s_k{d['k']}_overlay.png"
        plt.imsave(p, np.zeros((8, 8)))
        jsons.append(str(j))
        pngs.append(str(p))
    return ["--metrics", *jsons, "--overlays", *pngs, "--prefix", "s"]


class TestChoose:
    def test_lowest_score_wins(self):
        assert choose([m(3, 6, 0.5, 0.4, 0.3), m(4, 4, 0, 0.05, 0.02), m(5, 4, 0, 0.3, 0.1)])["k"] == 4

    def test_zero_cores_never_wins(self):
        assert score(m(7, 0, 1, None, None)) == math.inf
        assert choose([m(6, 0, 1, None, None), m(7, 9, 1.25, 0.9, 0.8)])["k"] == 7

    def test_tie_goes_to_smaller_k(self):
        assert choose([m(5, 4, 0, 0.1, 0.1), m(4, 4, 0, 0.1, 0.1)])["k"] == 4


class TestWarning:
    @pytest.mark.parametrize("ce,de,warns", [(0.1, 0.25, False), (0.11, 0, True), (0, 0.26, True)])
    def test_thresholds(self, ce, de, warns):
        assert (warning(m(4, 4, ce, de, 0)) is not None) == warns


class TestMain:
    def test_outputs(self, tmp_path, monkeypatch):
        args = write_sweep(
            tmp_path, [m(3, 5, 0.25, 0.07, 0.34), m(4, 4, 0, 0.03, 0.02), m(5, 4, 0, 0.2, 0.1)]
        )
        monkeypatch.chdir(tmp_path)
        main(args)
        assert json.loads((tmp_path / "s_selection.json").read_text()) == {
            "downsample_factor": 4,
            "warning": None,
        }
        with (tmp_path / "s_sweep.tsv").open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        assert list(rows[0]) == [
            "k", "um_per_px", "n_cores", "count_error", "diam_mm", "diam_error", "size_cv",
            "crop_ratio", "core_px_at_k", "score", "selected", "warning",
        ]  # fmt: skip
        assert [r["k"] for r in rows] == ["4", "5", "3"]
        assert [r["selected"] for r in rows] == ["true", "false", "false"]
        assert (tmp_path / "s_sweep_overlays.png").stat().st_size > 0

    def test_poor_winner_warns_but_selects(self, tmp_path, monkeypatch, capsys):
        args = write_sweep(tmp_path, [m(4, 6, 0.5, 0.4, 0.3), m(5, 7, 0.75, 0.5, 0.4)])
        monkeypatch.chdir(tmp_path)
        main(args)
        selection = json.loads((tmp_path / "s_selection.json").read_text())
        assert selection["downsample_factor"] == 4
        assert "6 cores" in selection["warning"]
        assert "6 cores" in capsys.readouterr().err

    def test_all_zero_cores_exits(self, tmp_path, monkeypatch):
        args = write_sweep(tmp_path, [m(k, 0, 1, None, None) for k in (3, 4, 5)])
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit, match="no downsample factor detected any core"):
            main(args)

    def test_tsv_rounds_floats(self, tmp_path, monkeypatch):
        """Pixel sizes come from float32 OME metadata; 20.799999237 should read 20.8."""
        noisy = {**m(5, 4, 0, 0.0329391436, 0.1120454839), "um_per_px": 20.799999237060547}
        args = write_sweep(tmp_path, [noisy])
        monkeypatch.chdir(tmp_path)
        main(args)
        with (tmp_path / "s_sweep.tsv").open() as f:
            row = next(csv.DictReader(f, delimiter="\t"))
        assert row["um_per_px"] == "20.8"
        assert row["diam_error"] == "0.0329"
