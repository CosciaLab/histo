"""The Ashlar stitching and registration section, from a hand-made --qc-output directory.

The layout mirrors josenimo/ashlar's qc.py (schema 1) on a 2x2-tile, 2-cycle slide.
"""

import csv
import json

import pytest
from qc_report import ASHLAR_QC_SCHEMA, build, load_registration, registration_section
from test_qc_report import minimal_metrics

TILES = [
    "cycle",
    "tile",
    "nominal_y",
    "nominal_x",
    "y",
    "x",
    "shift_y",
    "shift_x",
    "error",
    "model_distance_um",
    "angle",
    "reference_tile",
    "discard_error",
    "discard_background",
    "discard_shift",
    "foreground",
    "foreground_energy",
    "component",
    "tree_degree",
]
EDGES = [
    "t1",
    "t2",
    "dy",
    "dx",
    "shift_um",
    "error_raw",
    "error_final",
    "reject_reason",
    "in_tree",
    "fg_t1",
    "fg_t2",
]


def percentiles(*values):
    return dict(zip(("p50", "p95", "p100"), values, strict=False))


def summary(**over):
    s = {
        "schema_version": ASHLAR_QC_SCHEMA,
        "ashlar_version": "1.22.0+jose.1",
        "pixel_size_um": 0.65,
        "tile_size": [100, 100],
        "mosaic_shape": [190, 190],
        "warnings": [],
        "stitching": {
            "n_tiles": 4,
            "n_edges": 4,
            "n_edges_accepted": 4,
            "n_edges_rejected_error": 0,
            "n_edges_rejected_shift": 0,
            "max_error": 2.9,
            "null_error_percentiles": {"p1": 2.9, "p5": 3.1, "p50": 3.4},
            "edge_error_percentiles": {"p5": 0.5, "p50": 0.6, "p95": 0.8},
            "edges_like_null_fraction": 0.0,
            "n_components": 1,
            "n_tiles_outside_largest_component": 0,
            "stage_model": {"scale_y": 1.0, "scale_x": 0.999, "rotation_deg": 0.1, "shear_deg": 0.0},
            "model_residual_um_percentiles": percentiles(0.4, 0.6, 0.7),
            "n_foreground_tiles": 3,
        },
        "registration": [
            {
                "cycle": 1,
                "n_tiles": 4,
                "cycle_offset_um": [-42.0, -34.1],
                "cycle_angle": -0.52,
                "tile_angle_mad": None,
                "n_discard": 1,
                "n_discard_error": 0,
                "n_discard_background": 1,
                "n_discard_shift": 0,
                "n_kept_like_null": 0,
                "discard_fraction": 0.25,
                "residual_um_percentiles": percentiles(1.4, 1.9, 2.0),
            }
        ],
        "images": {"thumbnails": [], "overlays": ["overlay_cycle1.jpg"]},
    }
    s.update(over)
    return s


def write_qc(path, qc=None, reject=None):
    """Write a qc.json plus tables; reject maps an edge index to its rejection reason."""
    path.mkdir()
    (path / "qc.json").write_text(json.dumps(qc or summary()))
    pos = {0: (0, 0), 1: (0, 90), 2: (90, 0), 3: (90, 90)}
    with (path / "tiles.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(TILES)
        for t, (y, x) in pos.items():
            w.writerow([0, t, y, x, y, x, 0, 0, "", 0.4, "", "", "", "", "", int(t != 3), 7.5, 0, 1])
            w.writerow(
                [
                    1,
                    t,
                    y,
                    x,
                    y - 60,
                    x - 50,
                    0.1,
                    0.2,
                    0.6,
                    1.4,
                    "",
                    t,
                    0,
                    int(t == 3),
                    0,
                    int(t != 3),
                    "",
                    "",
                    "",
                ]
            )
    reject = reject or {}
    with (path / "edges.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(EDGES)
        for i, (a, b) in enumerate([(0, 1), (0, 2), (1, 3), (2, 3)]):
            reason = reject.get(i, "none")
            w.writerow(
                [a, b, 0.5, -0.5, 0.46, 0.6, "" if reason != "none" else 0.6, reason, int(i < 3), 1, 1]
            )
    # A JPEG header is enough: the report only base64-inlines it.
    (path / "overlay_cycle1.jpg").write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    (path / "s1_ashlar_report.pdf").write_bytes(b"%PDF-1.4")
    return path


class TestLoad:
    def test_reads_tables_images_and_pdf(self, tmp_path):
        reg = load_registration(write_qc(tmp_path / "s1_ashlar_qc"))
        assert reg["available"]
        assert len(reg["tiles"]) == 8
        assert len(reg["edges"]) == 4
        assert [p.name for p in reg["overlays"]] == ["overlay_cycle1.jpg"]
        assert reg["pdf"] == "s1_ashlar_report.pdf"

    def test_missing_dir_contents_is_stated(self, tmp_path):
        (tmp_path / "empty").mkdir()
        reg = load_registration(tmp_path / "empty")
        assert not reg["available"]
        assert "no qc.json" in reg["reason"]

    def test_stub_output_is_not_rendered_as_data(self, tmp_path):
        d = tmp_path / "stub"
        d.mkdir()
        (d / "qc.json").write_text('{"schema_version": 1, "stub": true}')
        assert load_registration(d) == {"available": False, "reason": "stub run"}

    def test_unknown_schema_is_refused_not_guessed(self, tmp_path):
        reg = load_registration(write_qc(tmp_path / "q", summary(schema_version=99)))
        assert not reg["available"]
        assert "schema 99" in reg["reason"]


class TestSection:
    def test_clean_run(self, tmp_path):
        html = registration_section(load_registration(write_qc(tmp_path / "s1_ashlar_qc")))
        assert "Stitching and registration" in html
        assert "all 4 pairs accepted" in html
        assert "Cycle 2: every foreground tile registered" in html
        assert "data:image/jpeg;base64," in html
        assert "../preprocessing/registration/s1_ashlar_qc/s1_ashlar_report.pdf" in html
        assert "Show as table" in html

    def test_rejected_pair_is_drawn_and_counted(self, tmp_path):
        qc = summary()
        qc["stitching"].update(n_edges_accepted=3, n_edges_rejected_error=1)
        html = registration_section(load_registration(write_qc(tmp_path / "q", qc, {3: "error"})))
        assert "1 of 4 rejected: 1 on error, 0 on shift" in html
        assert "stroke-dasharray" in html
        assert "rejected (error)" in html

    def test_failed_cycle_and_warnings_are_named(self, tmp_path):
        qc = summary(warnings=["Some neighboring tiles have zero overlap."])
        qc["registration"][0].update(n_discard_shift=2, n_kept_like_null=1)
        html = registration_section(load_registration(write_qc(tmp_path / "q", qc)))
        assert "2 too far from the model, 1 kept but no better than chance" in html
        assert "Some neighboring tiles have zero overlap." in html

    def test_fragmented_mosaic_is_named(self, tmp_path):
        qc = summary()
        qc["stitching"].update(n_components=2, n_tiles_outside_largest_component=1)
        html = registration_section(load_registration(write_qc(tmp_path / "q", qc)))
        assert "2 components; 1 tile placed by the stage model alone" in html

    def test_absence_is_stated_not_hidden(self):
        html = registration_section({"available": False, "reason": "stub run"})
        assert "Not computed: stub run." in html

    def test_none_renders_nothing(self):
        assert registration_section(None) == ""


@pytest.mark.parametrize("with_registration", [False, True])
def test_whole_page_still_renders(tmp_path, with_registration):
    reg = load_registration(write_qc(tmp_path / "q")) if with_registration else None
    page = build(minimal_metrics(), registration=reg)
    assert page.rstrip().endswith("</html>")
    assert ("Stitching and registration" in page) is with_registration


def test_slide_report_carries_the_slide_registration(tmp_path):
    from merge_report import build as build_slide
    from test_merge_report import core

    reg = load_registration(write_qc(tmp_path / "slide_ashlar_qc"))
    page = build_slide("slide", [core("slide_core001"), core("slide_core002")], reg)
    assert "Stitching and registration" in page
    assert "Stitching and registration" not in build_slide("slide", [core("slide_core001")])
