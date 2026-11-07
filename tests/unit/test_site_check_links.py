"""Tests for site_check_links.broken_links on a tiny built-HTML tree."""

from site_check_links import broken_links


def page(root, rel, body):
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"<html><body>{body}</body></html>")


class TestBrokenLinks:
    def test_good_links_pass(self, tmp_path):
        page(tmp_path, "index.html", '<a href="/histo/usage">u</a><a href="/histo/usage#sec">s</a>')
        page(tmp_path, "usage/index.html", '<h2 id="sec">x</h2><a href="#sec">self</a><a href="../">up</a>')
        assert broken_links(tmp_path) == []

    def test_missing_page(self, tmp_path):
        page(tmp_path, "index.html", '<a href="/histo/nope">n</a>')
        out = broken_links(tmp_path)
        assert len(out) == 1 and "/histo/nope" in out[0] and "missing page" in out[0]

    def test_missing_anchor(self, tmp_path):
        page(tmp_path, "index.html", '<a href="/histo/usage#gone">n</a><a href="#nothing">m</a>')
        page(tmp_path, "usage/index.html", '<h2 id="sec">x</h2>')
        out = broken_links(tmp_path)
        assert len(out) == 2 and all("missing anchor" in o for o in out)

    def test_escaping_base_is_broken(self, tmp_path):
        page(tmp_path, "index.html", '<a href="/histo/../README.md">r</a>')
        assert len(broken_links(tmp_path)) == 1

    def test_external_and_mailto_ignored(self, tmp_path):
        page(tmp_path, "index.html", '<a href="https://x.org/a">e</a><a href="mailto:a@b.c">m</a>')
        assert broken_links(tmp_path) == []

    def test_links_outside_base_url_ignored(self, tmp_path):
        page(tmp_path, "index.html", '<a href="/other/thing">o</a>')
        assert broken_links(tmp_path) == []
