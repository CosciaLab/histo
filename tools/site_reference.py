#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Generate the docs site's reference pages from the schemas, meta.yml files and containers.tsv.

Writes site/_generated/ (git-ignored); the site includes those files.
"""

import csv
import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

# Slug of a how-it-works page -> module dirs (relative to the repo root) whose facts it shows.
PAGES: dict[str, list[str]] = {
    "basicpy": ["modules/nf-core/basicpy"],
    "ashlar": ["modules/nf-core/ashlar"],
    "coreograph": [
        "modules/nf-core/coreograph",
        "modules/local/coreograph_detect",
        "modules/local/coreograph_select",
    ],
    "backsub": ["modules/nf-core/backsub"],
    "spatialdata": [
        "modules/local/to_spatialdata",
        "modules/local/set_channel_names",
        "modules/local/write_segmentations",
        "modules/local/merge_spatialdata",
        "modules/local/publish_spatialdata",
    ],
    "tiling": [
        "modules/local/make_image_patches",
        "modules/local/tissue_segmentation",
        "modules/local/resolve",
    ],
    "cellpose": ["modules/local/segment_patch"],
    "instanseg": ["modules/local/segment_patch"],
    "projection": ["modules/local/project_channels"],
    "linking": ["modules/local/link_compartments"],
    "quantification": ["modules/local/aggregate"],
    "qc-report": [
        "modules/local/qc_metrics",
        "modules/local/qc_images",
        "modules/local/qc_report",
        "modules/local/compare_segmentations",
        "modules/local/merge_report",
    ],
}

# Pages whose modules' meta.yml names the wrapper (sopa) or a helper, not the tool the page is about.
# "package" is the conda name whose pin gives the Version; without a pin the cell stays blank.
TOOL_OVERRIDES: dict[str, dict[str, str]] = {
    "cellpose": {
        "name": "Cellpose",
        "homepage": "https://www.cellpose.org",
        "doi": "10.1101/2025.04.28.651001",
        "package": "cellpose",
    },
    "instanseg": {
        "name": "InstanSeg",
        "homepage": "https://github.com/instanseg/instanseg",
        "doi": "10.48550/arXiv.2408.15954",
        "package": "instanseg",
    },
    "qc-report": {"name": "pipeline scripts (`bin/`)"},
}


def _cell(text: object) -> str:
    """One-line table cell: collapse whitespace, escape pipes."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _type(prop: dict) -> str:
    t = prop.get("type", "")
    return " | ".join(t) if isinstance(t, list) else str(t)


def _default(prop: dict) -> str:
    value = prop.get("default")
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # the schema linter writes 2000 as 2000.0
    return str(value)


def _render_parameter(name: str, prop: dict) -> str:
    # MyST has no {#id} heading syntax; a (name)= target gives the heading its anchor.
    lines = [f"({name})=", f"### `{name}`", "", "Type", f": `{_type(prop)}`", "", "Default"]
    lines += [f": `{_default(prop)}`", ""]
    if "enum" in prop:
        values = ", ".join(f"`{v}`" for v in prop["enum"])
        lines += ["Allowed", f": {values}", ""]
    if prop.get("description"):
        lines += [prop["description"].strip(), ""]
    if prop.get("help_text"):
        lines += [prop["help_text"].strip(), ""]
    return "\n".join(lines)


def render_parameters(schema: dict) -> str:
    """One section per parameter group, in allOf order; hidden parameters go in one dropdown."""
    defs = schema["$defs"]
    out: list[str] = []
    hidden: list[tuple[str, dict]] = []
    for entry in schema["allOf"]:
        group = defs[entry["$ref"].rsplit("/", 1)[-1]]
        shown = []
        for name, prop in group["properties"].items():
            (hidden if prop.get("hidden") else shown).append((name, prop))
        if not shown:  # an all-hidden group would render an empty section
            continue
        out += [f"## {group['title']}", ""]
        if group.get("description"):
            out += [group["description"].strip(), ""]
        out += [_render_parameter(n, p) for n, p in shown]
    if hidden:
        out += [":::{dropdown} Hidden parameters", ""]
        out += [_render_parameter(n, p) for n, p in hidden]
        out += [":::", ""]
    return "\n".join(out)


def render_sheet(schema: dict, title: str) -> str:
    """A Column | Required | Type | Description table from an array schema's items."""
    items = schema["items"]
    required = set(items.get("required", []))
    lines = [f"## {title}", ""]
    if schema.get("description"):
        lines += [schema["description"].strip(), ""]
    lines += ["| Column | Required | Type | Description |", "| --- | --- | --- | --- |"]
    for name, prop in items["properties"].items():
        kind = _type(prop)
        if "enum" in prop:
            kind += ": " + ", ".join(str(v) for v in prop["enum"])
        req = "yes" if name in required else "no"
        lines.append(f"| `{name}` | {req} | {_cell(kind)} | {_cell(prop.get('description', ''))} |")
    lines.append("")
    return "\n".join(lines)


def _read_rows(containers_tsv: Path) -> list[dict]:
    with containers_tsv.open() as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def _tool(module_dir: Path) -> dict:
    """First tool of meta.yml, or just the directory name when the module has none."""
    meta = module_dir / "meta.yml"
    if meta.is_file():
        tools = (yaml.safe_load(meta.read_text()) or {}).get("tools") or []
        if tools:
            name, info = next(iter(tools[0].items()))
            return {"name": name, **(info or {})}
    return {"name": module_dir.name}


def _conda_packages(conda: str) -> list[tuple[str, str]]:
    """(name, version) per conda entry, skipping python/pip and stripping extras."""
    pkgs = []
    for entry in conda.split(","):
        m = re.match(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==?(.+)$", entry.strip())
        if m and m.group(1) not in ("python", "pip"):
            pkgs.append((m.group(1), m.group(2)))
    return pkgs


def _pin(package: str, conda: str) -> str:
    """The version the conda spec pins for the package, else ""."""
    m = re.search(rf"(?:^|[,\s]){re.escape(package)}(?:\[[^\]]*\])?==?([^,\s]+)", conda)
    return m.group(1) if m else ""


def _version(tool: str, conda: str, docker_uri: str) -> str:
    """The version the conda spec pins for the tool, else the image tag."""
    if pin := _pin(tool, conda):
        return pin
    tag = docker_uri.rsplit(":", 1)[-1] if ":" in docker_uri else ""
    return tag if re.match(r"v?\d+\.\d", tag) else ""  # hash tags are not versions


def render_module_facts(module_dirs: list[Path], containers_tsv: Path, override: dict | None = None) -> str:
    """Module | Tool | Version | Container | Paper, one row per module dir; override from TOOL_OVERRIDES."""
    rows = _read_rows(containers_tsv)
    lines = ["| Module | Tool | Version | Container | Paper |", "| --- | --- | --- | --- | --- |"]
    for d in module_dirs:
        rel = "/".join(d.parts[-3:])  # modules/<local|nf-core>/<name>, as containers.tsv writes it
        row = next((r for r in rows if rel in r["modules"].split(",")), {})
        tool = dict(override) if override else _tool(d)
        if not override and not (d / "meta.yml").is_file() and row.get("conda"):
            pkgs = _conda_packages(row["conda"])
            if pkgs:
                tool["name"] = pkgs[0][0]
        name = tool["name"]
        if tool.get("homepage"):
            name = f"[{name}]({tool['homepage']})"
        if override:
            version = _pin(override["package"], row.get("conda", "")) if "package" in override else ""
        else:
            version = _version(tool["name"], row.get("conda", ""), row.get("docker_uri", "")) if row else ""
        doi = tool.get("doi")
        paper = f"[{doi}](https://doi.org/{doi})" if doi else ""
        container = f"`{row['docker_uri']}`" if row else "none (runs on the host)"
        lines.append(f"| {d.name.upper()} | {_cell(name)} | {_cell(version)} | {container} | {paper} |")
    lines.append("")
    return "\n".join(lines)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def main(repo: Path = REPO) -> None:
    out = repo / "site" / "_generated"
    (out / "modules").mkdir(parents=True, exist_ok=True)
    (out / "parameters.md").write_text(render_parameters(_load(repo / "nextflow_schema.json")))
    sheets = [
        ("Cycle sheet", "schema_input_cycle.json"),
        ("Stitched-image sheet", "schema_input.json"),
        ("Marker sheet", "schema_marker.json"),
    ]
    (out / "samplesheet.md").write_text(
        "\n".join(render_sheet(_load(repo / "assets" / f), t) for t, f in sheets)
    )
    for slug, dirs in PAGES.items():
        facts = render_module_facts(
            [repo / d for d in dirs], repo / "containers.tsv", TOOL_OVERRIDES.get(slug)
        )
        (out / "modules" / f"{slug}.md").write_text(facts)


if __name__ == "__main__":
    main()
