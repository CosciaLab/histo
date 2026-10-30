import json
import re
from pathlib import Path

import yaml
from params_template_compact import render

REPO = Path(__file__).resolve().parents[2]

SCHEMA = {
    "title": "test pipeline parameters",
    "$defs": {
        "io": {
            "title": "Input/output options",
            "required": ["input"],
            "properties": {
                "input": {"type": "string", "description": "Samplesheet."},
                "outdir": {"type": "string", "description": "Output\n  directory."},
            },
        },
        "seg": {
            "title": "Segmentation",
            "properties": {
                "use_cellpose": {"type": "boolean", "default": False, "description": "Run Cellpose."},
                "mode": {
                    "type": "string",
                    "default": "otsu",
                    "enum": ["otsu", "saturation"],
                    "description": "Method.",
                },
                "device": {"type": "string", "description": "Device, e.g. `cpu`. Ignored without a GPU."},
                "extra_args": {
                    "type": "string",
                    "default": "--a-very-long-flag 1 --another-long-flag 2 --x",
                    "description": "Args.",
                },
                "patch_overlap_pixel": {"type": "integer", "default": 50, "description": "Overlap."},
            },
        },
    },
    "allOf": [{"$ref": "#/$defs/io"}, {"$ref": "#/$defs/seg"}],
}

PARAM_LINE = re.compile(r"^# (\w+): (.*?) +# (.*)$")


def param_lines(text):
    return [line for line in text.splitlines() if PARAM_LINE.match(line)]


def test_every_param_is_one_line_with_its_description():
    lines = param_lines(render(SCHEMA))
    assert [PARAM_LINE.match(line)[1] for line in lines] == [
        "input",
        "outdir",
        "use_cellpose",
        "mode",
        "device",
        "extra_args",
        "patch_overlap_pixel",
    ]
    assert PARAM_LINE.match(lines[1])[3] == "Output directory."


def test_required_and_choices_are_marked():
    text = render(SCHEMA)
    assert "# Samplesheet. Required." in text
    assert "# Method. One of: otsu, saturation." in text


def test_only_the_first_sentence_is_kept():
    text = render(SCHEMA)
    assert "# Device, e.g. `cpu`.\n" in text
    assert "Ignored without a GPU" not in text


def test_comments_align_within_a_group_and_long_defaults_overflow():
    seg = param_lines(render(SCHEMA).split("## Segmentation")[1])
    short = [line for line in seg if "extra_args" not in line]
    assert len({line.index(" # ") for line in short}) == 1
    assert next(line for line in seg if "extra_args" in line).index(" # ") > short[0].index(" # ")


def test_uncommented_lines_parse_to_the_schema_defaults():
    schema = json.loads((REPO / "nextflow_schema.json").read_text())
    text = render(schema)
    uncommented = "\n".join(line[2:] for line in param_lines(text))
    expected = {k: p.get("default") for d in schema["$defs"].values() for k, p in d["properties"].items()}
    assert yaml.safe_load(uncommented) == expected


def test_committed_file_is_current():
    schema = json.loads((REPO / "nextflow_schema.json").read_text())
    assert (REPO / "assets/params_template_compact.yml").read_text() == render(schema)
