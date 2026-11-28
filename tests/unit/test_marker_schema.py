"""The marker sheet's uniprot_id pattern accepts accessions and rejects gene names."""

import json
import re
from pathlib import Path

import pytest

SCHEMA = Path(__file__).resolve().parents[2] / "assets/schema_marker.json"
PATTERN = json.loads(SCHEMA.read_text())["items"]["properties"]["uniprot_id"]["pattern"]


@pytest.mark.parametrize("value", ["P08575", "P08575-8", "A0A024R161", "Q9Y6K9"])
def test_accepts_accession(value):
    assert re.fullmatch(PATTERN, value)


@pytest.mark.parametrize("value", ["CD3", "ELANE", "p08575", "P08575-", "P0857"])
def test_rejects_non_accession(value):
    assert not re.fullmatch(PATTERN, value)
