"""Tests for site_reference: the generator for the docs site's reference pages."""

import json
from pathlib import Path

import pytest
from site_reference import PAGES, REPO, main, render_module_facts, render_parameters, render_sheet

FIXTURE = Path(__file__).parent / "fixtures" / "site_schema.json"


@pytest.fixture
def schema():
    return json.loads(FIXTURE.read_text())


def test_parameter_anchor_and_default(schema):
    md = render_parameters(schema)
    assert "(patch_width_pixel)=\n### `patch_width_pixel`\n" in md
    assert "2000" in md


def test_missing_default_says_none_not_python_none(schema):
    md = render_parameters(schema)
    assert "None" not in md
    assert "none" in md


def test_hidden_parameters_in_dropdown_only(schema):
    md = render_parameters(schema)
    head, _, tail = md.partition(":::{dropdown} Hidden parameters")
    assert "`hidden_flag`" not in head and "`hidden_flag`" in tail


def test_help_text_rendered(schema):
    assert "Pick at least the largest expected cell diameter." in render_parameters(schema)


def test_enum_listed(schema):
    md = render_parameters(schema)
    assert "`cellpose`" in md and "`instanseg`" in md


def test_group_heading(schema):
    assert "## Tiling options" in render_parameters(schema)


def test_sheet_marks_required():
    schema = json.loads((REPO / "assets/schema_marker.json").read_text())
    md = render_sheet(schema, "Marker sheet")
    assert md.startswith("## Marker sheet")
    row = next(line for line in md.splitlines() if line.startswith("| `channel_role`"))
    assert "yes" in row


def test_module_facts_ashlar():
    md = render_module_facts([REPO / "modules/nf-core/ashlar"], REPO / "containers.tsv")
    assert "ashlar" in md and "10.1093/bioinformatics/btac544" in md
    assert "1.22.1" in md


def test_module_facts_conda_pin_beats_image_tag():
    md = render_module_facts([REPO / "modules/local/segment_patch"], REPO / "containers.tsv")
    assert "2.3.0" in md and "SEGMENT_PATCH" in md


def test_module_without_meta_or_container_row():
    md = render_module_facts([REPO / "modules/local/publish_spatialdata"], REPO / "containers.tsv")
    assert "PUBLISH_SPATIALDATA" in md


def test_pages_point_at_existing_modules():
    for dirs in PAGES.values():
        for d in dirs:
            assert (REPO / d).is_dir(), d


def test_main_on_real_repo(tmp_path):
    import shutil

    for sub in ("assets", "modules"):
        shutil.copytree(REPO / sub, tmp_path / sub)
    shutil.copy(REPO / "nextflow_schema.json", tmp_path)
    shutil.copy(REPO / "containers.tsv", tmp_path)
    main(tmp_path)
    out = tmp_path / "site/_generated"
    params = (out / "parameters.md").read_text()
    for group in json.loads((REPO / "nextflow_schema.json").read_text())["$defs"].values():
        for name in group["properties"]:
            assert f"`{name}`" in params
    sheets = (out / "samplesheet.md").read_text()
    assert "Cycle" in sheets and "Stitched" in sheets and "Marker" in sheets
    for slug in PAGES:
        assert (out / "modules" / f"{slug}.md").is_file()


def test_no_meta_tool_and_version_come_from_conda():
    cells = [
        c.strip()
        for c in render_module_facts([REPO / "modules/local/to_spatialdata"], REPO / "containers.tsv")
        .splitlines()[2]
        .split("|")[1:-1]
    ]
    assert cells[:3] == ["TO_SPATIALDATA", "sopa", "2.2.9"]


def test_no_meta_no_conda_uses_dir_name_and_image_tag():
    cells = [
        c.strip()
        for c in render_module_facts([REPO / "modules/local/coreograph_detect"], REPO / "containers.tsv")
        .splitlines()[2]
        .split("|")[1:-1]
    ]
    assert cells[:3] == ["COREOGRAPH_DETECT", "coreograph_detect", "2.4.6"]


def test_hash_image_tag_is_not_a_version():
    from site_reference import _version

    assert _version("x", "", "registry/img:54a97bc5a187152d") == ""
    assert _version("x", "", "registry/img:v0.5.1") == "v0.5.1"


def test_module_without_container_row_runs_on_host():
    cells = [
        c.strip()
        for c in render_module_facts([REPO / "modules/local/publish_spatialdata"], REPO / "containers.tsv")
        .splitlines()[2]
        .split("|")[1:-1]
    ]
    assert cells == ["PUBLISH_SPATIALDATA", "publish_spatialdata", "", "none (runs on the host)", ""]


def test_all_hidden_group_has_no_heading():
    schema = {
        "$defs": {
            "inst": {
                "title": "Institutional config options",
                "properties": {"h": {"hidden": True, "type": "string"}},
            }
        },
        "allOf": [{"$ref": "#/$defs/inst"}],
    }
    md = render_parameters(schema)
    head, _, tail = md.partition(":::{dropdown} Hidden parameters")
    assert "## Institutional" not in head and "`h`" in tail
