#!/usr/bin/env python3
"""Finish the two parameter templates after nf-core pipelines create-params-file.

assets/params_template.yml is nf-core's, with full descriptions; this adds the null note to its
header. assets/params_template_compact.yml has every parameter on one line; nf-core has no such
layout, so this writes it. Run by the params-templates prek hook.

Usage:
    tools/params_templates.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# A sentence ends at . ! or ? before a capital letter, but not after e.g. or i.e.
SENTENCE_END = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?])\s+(?=[A-Z])")
# Longer "# key: default" parts overflow rather than push the whole group's comments right.
ALIGN_MAX = 40

# nf-core prints null for every parameter without a schema default, including false booleans.
NULL_NOTE = [
    "null means not set. A true/false parameter at null is off. Any other",
    "parameter at null is not passed on, so the pipeline or tool uses its own",
    "default; docs/usage.md lists the few you must set.",
]

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "nextflow_schema.json"
COMPACT = REPO / "assets/params_template_compact.yml"
NFCORE = REPO / "assets/params_template.yml"


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
    if schema.get("properties"):
        raise ValueError(
            f"parameters outside any group: {sorted(schema['properties'])}. Both templates would "
            "leave them out; move them into a group with nf-core pipelines schema build."
        )
    out = [
        f"# {schema['title']}: every parameter on one line, with its default.",
        "# Uncomment and edit what you change, then pass the file to -params-file.",
        "# Full descriptions: assets/params_template.yml. Generated from nextflow_schema.json by",
        "# tools/params_templates.py; do not edit by hand.",
        "#",
        *(f"# {line}" for line in NULL_NOTE),
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


def add_note(text: str) -> str:
    """Insert NULL_NOTE above the rule that closes nf-core's header; no-op if already there."""
    if f"##     {NULL_NOTE[0]}" in text:
        return text
    lines = text.split("\n")
    rule = next(i for i, line in enumerate(lines) if line.startswith("## ---"))
    lines[rule:rule] = ["##", *(f"##     {line}" for line in NULL_NOTE)]
    return "\n".join(lines)


def main() -> None:
    COMPACT.write_text(render(json.loads(SCHEMA.read_text())))
    NFCORE.write_text(add_note(NFCORE.read_text()))


if __name__ == "__main__":
    main()
