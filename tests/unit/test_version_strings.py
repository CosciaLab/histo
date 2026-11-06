"""Every `-r vX.Y.Z` in the docs matches manifest.version, so a release bump cannot miss a copy."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _manifest_version() -> str:
    manifest = re.search(r"^manifest\s*\{(.*?)^\}", (REPO / "nextflow.config").read_text(), re.S | re.M)
    return re.search(r"^\s*version\s*=\s*['\"]([^'\"]+)['\"]", manifest.group(1), re.M).group(1)


def _doc_files() -> list[Path]:
    site = [p for p in (REPO / "site").rglob("*.md") if not {"_build", "node_modules"} & set(p.parts)]
    return site + [REPO / "docs/usage.md", REPO / "README.md"]


def test_run_commands_use_manifest_version():
    version = _manifest_version()
    # On dev the manifest carries a dev suffix while the docs still name the last release.
    if "dev" in version:
        pytest.skip(f"manifest.version {version} is a dev version; checked at release")
    found = {
        f"{p.relative_to(REPO)}:{n}": m
        for p in _doc_files()
        for n, line in enumerate(p.read_text().splitlines(), 1)
        for m in re.findall(r"-r (v\d+\.\d+\.\d+[\w.+-]*)", line)
    }
    assert found, "no -r vX.Y.Z found; did the docs move?"
    stale = {k: v for k, v in found.items() if v != f"v{version}"}
    assert not stale, f"-r strings differ from manifest.version {version}: {stale}"
