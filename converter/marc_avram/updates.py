"""Parse the LoC "MARC Format Documentation Overview" page into a per-format
map of update number -> change-list description page, for the diff viewer.

The overview (https://www.loc.gov/marc/marcdocz.html, saved locally) lists,
for each full format, one ``<li>`` per integrated update::

    <li>Update No. 13 (September 2011)
        (<a href="up13bibliographic/bdapndxg.html">List of changes included</a>)</li>

plus a "Base edition" entry, and one combined entry for Updates 10 & 11.
Hrefs are relative to ``https://www.loc.gov/marc/`` (some are
protocol-relative ``//www.loc.gov/...``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_BASE = "https://www.loc.gov/marc/"

# the full-format section headers, in document order
_SECTION = re.compile(
    r'<a href="//www\.loc\.gov/marc/'
    r'(?P<slug>bibliographic|authority|holdings|classification|community)/"'
    r'[^>]*>\s*MARC 21 Format for', re.I)

_LI = re.compile(r"<li>(.*?)</li>", re.S | re.I)
_HREF = re.compile(r'<a href="([^"]+)"', re.I)
_UPDATE = re.compile(r"Update\s+No\.\s*(\d+)\s*\(([^)]+)\)", re.I)
_EDITION = re.compile(r"Base\s+(?:edition|text)\s*\(([^)]+)\)", re.I)


def _absolute(href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith(("http://", "https://")):
        return href
    return _BASE + href


def parse_overview(html: str) -> dict[str, dict[str, dict]]:
    """``{format slug: {"base"|"<n>": {label, date, url}}}``."""
    marks = [(m.start(), m.group("slug")) for m in _SECTION.finditer(html)]
    out: dict[str, dict[str, dict]] = {}
    for (start, slug), end in zip(marks, [p for p, _ in marks[1:]] + [len(html)]):
        if slug in out:        # the "Concise" sections repeat the slug; skip
            continue
        entries: dict[str, dict] = {}
        for li in _LI.findall(html[start:end]):
            href = _HREF.search(li)
            if href is None or "changes" not in re.sub(r"<[^>]+>", "", li).lower():
                continue
            url = _absolute(href.group(1))
            for num, date in _UPDATE.findall(li):
                entries[num] = {"label": f"Update No. {num}",
                                "date": date.strip(), "url": url}
            m = _EDITION.search(li)
            if m:
                entries["base"] = {"label": "Base edition",
                                   "date": m.group(1).strip(), "url": url}
        if entries:
            out[slug] = entries
    return out


def write_updates(overview_html: str | Path, out_dir: str | Path) -> Path:
    """Write ``updates.json`` into ``out_dir`` (fetched by the viewer)."""
    data = parse_overview(Path(overview_html).read_text(encoding="utf-8",
                                                        errors="replace"))
    out = Path(out_dir) / "updates.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return out
