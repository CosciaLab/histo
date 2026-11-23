#!/usr/bin/env python3
"""Check internal links and anchors in the built docs site (myst --strict does not).

Usage: tools/site_check_links.py [HTML_ROOT] [--base-url /histo]    # exit 1 if any link is broken
"""

from __future__ import annotations

import argparse
import posixpath
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a":
            if a.get("name"):
                self.ids.add(a["name"])
            if a.get("href"):
                self.hrefs.append(a["href"])


def _parse(path: Path) -> _Collector:
    c = _Collector()
    c.feed(path.read_text(encoding="utf-8", errors="replace"))
    return c


def _find_page(root: Path, rel: str) -> Path | None:
    for cand in (root / rel / "index.html", root / f"{rel}.html", root / rel):
        if cand.is_file():
            return cand
    return None


def broken_links(html_root: Path, base_url: str = "/histo") -> list[str]:
    html_root = Path(html_root)
    base = base_url.rstrip("/")
    cache: dict[Path, _Collector] = {}
    problems: list[str] = []

    for src in sorted(html_root.rglob("*.html")):
        src_rel = src.relative_to(html_root).as_posix()
        # URL directory of this page, relative links resolve against it
        src_dir = posixpath.dirname(src_rel)
        for href in _parse(src).hrefs:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc:
                continue
            if not parts.path:
                if not parts.fragment:
                    continue
                page_file = src
            else:
                if parts.path.startswith("/"):
                    full = parts.path
                else:
                    full = posixpath.join(f"{base}/{src_dir}", parts.path)
                full = posixpath.normpath(full)
                if full != base and not full.startswith(base + "/"):
                    # outside the site: ignore a plain foreign absolute path, flag one that escapes via ..
                    if ".." in parts.path.split("/") or not parts.path.startswith("/"):
                        problems.append(f"{src_rel}: {href} -> missing page (leaves {base})")
                    continue
                rel = full[len(base) :].strip("/")
                page_file = _find_page(html_root, rel)
                if page_file is None:
                    problems.append(f"{src_rel}: {href} -> missing page")
                    continue
            if parts.fragment:
                if page_file not in cache:
                    cache[page_file] = _parse(page_file)
                if parts.fragment not in cache[page_file].ids:
                    problems.append(f"{src_rel}: {href} -> missing anchor")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html_root", nargs="?", default="_build/html")
    ap.add_argument("--base-url", default="/histo")
    args = ap.parse_args()
    problems = broken_links(Path(args.html_root), args.base_url)
    for p in problems:
        print(p)
    print(f"{len(problems)} broken internal link(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
