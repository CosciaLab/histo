"""Every parameter a startup check reads must state its rule in the schema's help_text."""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UTILS_NF = REPO / "subworkflows/local/utils_nfcore_histo_pipeline/main.nf"
SCHEMA = REPO / "nextflow_schema.json"

CHECK_FUNCS = ["validateParams", "validateMarkersheet", "validateProjectionGroups", "checkReferenceChannels"]
MARKERS = ("**Requires:**", "**Conflicts:**", "**Ignored unless:**")

# Read by a check but needing no rule line. Keep minimal; each entry needs a reason.
WARN_ONLY = {
    # name: reason
}


def schema_properties():
    schema = json.loads(SCHEMA.read_text())
    props = {}
    for group in schema.get("$defs", schema.get("definitions", {})).values():
        props.update(group.get("properties", {}))
    return props


def schema_property_names():
    return set(schema_properties())


def help_text(name):
    return schema_properties()[name].get("help_text", "")


def params_in_functions(path, names):
    """Parameter names read inside the given top-level `def` bodies of a Nextflow file."""
    found = set()
    body = None
    for line in Path(path).read_text().splitlines():
        if line.startswith("def "):
            m = re.match(r"def (\w+)\(", line)
            body = m is not None and m.group(1) in names
        if not body:
            continue
        found.update(m[0] or m[1] for m in re.findall(r"params\.(\w+)|params\[['\"](\w+)['\"]\]", line))
        if "STAINING_BASED_METHODS =" in line:
            found.update(re.findall(r"'(\w+)'", line.split("=", 1)[1]))
    return found


def test_every_checked_param_has_a_rule():
    names = params_in_functions(UTILS_NF, CHECK_FUNCS) & schema_property_names()
    missing = [n for n in sorted(names) if n not in WARN_ONLY and not any(m in help_text(n) for m in MARKERS)]
    assert not missing, f"add a rule line to help_text of: {missing}"


RULE_FORMAT = re.compile(
    r"(\*\*Requires:\*\* [^*]*\.)?(?: ?)(\*\*Conflicts:\*\* [^*]*\.)?(?: ?)(\*\*Ignored unless:\*\* [^*]*\.)?"
)


def test_rule_paragraph_format():
    bad = []
    for name, prop in schema_properties().items():
        text = prop.get("help_text", "")
        if not any(m in text for m in MARKERS):
            continue
        last = text.split("\n\n")[-1]
        if not last.startswith("**") or not RULE_FORMAT.fullmatch(last):
            bad.append(name)
        elif sum(text.count(m) for m in MARKERS) != sum(last.count(m) for m in MARKERS):
            bad.append(name)  # a marker outside the final paragraph
    assert not bad, f"rule paragraph malformed in help_text of: {bad}"
