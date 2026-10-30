#!/usr/bin/env python3
"""Write assets/params_template_compact.yml: every schema parameter on one line, with its default.

The short sibling of assets/params_template.yml, which nf-core generates with full descriptions.
nf-core has no compact layout, hence this script. Run by the params-template-compact prek hook.

Usage:
    tools/params_template_compact.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# A sentence ends at . ! or ? before a capital letter, but not after e.g. or i.e.
SENTENCE_END = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?])\s+(?=[A-Z])")
# Longer "# key: default" parts overflow rather than push the whole group's comments right.
ALIGN_MAX = 40

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "nextflow_schema.json"
OUT = REPO / "assets/params_template_compact.yml"


def describe(prop: dict, required: bool) -> str:
    """First sentence of the description, with required and enum choices appended."""
    text = SENTENCE_END.split(" ".join(prop.get("description", "").split()), maxsplit=1)[0]
    if text and not text.endswith((".", "?", "!")):
        text += "."
    if required:
        text += " Required."
    if "enum" in prop:
        text += " One of: " + ", ".join(str(v) for v in prop["enum"]) + "."
    return text.strip()


def render(schema: dict) -> str:
    """Render the template; uncommented, each line parses as YAML to the schema default."""
    out = [
        f"# {schema['title']}: every parameter on one line, with its default.",
        "# Uncomment and edit what you change, then pass the file to -params-file.",
        "# Full descriptions: assets/params_template.yml. Generated from nextflow_schema.json by",
        "# tools/params_template_compact.py; do not edit by hand.",
    ]
    for ref in schema["allOf"]:
        group = schema["$defs"][ref["$ref"].split("/")[-1]]
        required = set(group.get("required", []))
        # JSON is valid YAML and keeps strings quoted as nf-core's template does.
        rows = [
            (
                f"# {key}: {json.dumps(prop.get('default'), ensure_ascii=False)}",
                describe(prop, key in required),
            )
            for key, prop in group["properties"].items()
        ]
        width = max((len(lhs) for lhs, _ in rows if len(lhs) <= ALIGN_MAX), default=ALIGN_MAX)
        out += ["", f"## {group['title']}"]
        out += [f"{lhs.ljust(width)}  # {desc}" for lhs, desc in rows]
    return "\n".join(out) + "\n"


def main() -> None:
    OUT.write_text(render(json.loads(SCHEMA.read_text())))


if __name__ == "__main__":
    main()
