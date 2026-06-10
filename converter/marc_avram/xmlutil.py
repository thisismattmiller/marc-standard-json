"""Stages 1 & 2 — XML parsing, the FULL display filter, and text normalization.

The publishing XML uses a default namespace ``http://www.loc.gov/MARCDOC/`` for
structure and ``http://www.loc.gov/MARC21/slim`` for the embedded MARCXML
examples.  We strip namespaces so downstream code works with local names.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

# ---------------------------------------------------------------------------
# Parsing + namespace stripping
# ---------------------------------------------------------------------------


_PARSE_CACHE: dict[str, etree._Element] = {}


def parse(path: str | Path) -> etree._Element:
    """Parse a doc, strip namespaces, and apply the FULL filter in place.

    Results are cached by absolute path: a given file (e.g. ``ad008_base.xml``)
    is reused across many "as of update N" snapshots.  The parsed tree is only
    read after this call, so sharing it is safe."""
    key = str(Path(path).resolve())
    cached = _PARSE_CACHE.get(key)
    if cached is not None:
        return cached
    parser = etree.XMLParser(recover=True, resolve_entities=True, huge_tree=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    _strip_namespaces(root)
    apply_full_filter(root)
    _PARSE_CACHE[key] = root
    return root


def _strip_namespaces(root: etree._Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    etree.cleanup_namespaces(root)


# ---------------------------------------------------------------------------
# FULL display filter
# ---------------------------------------------------------------------------


def in_full(el: etree._Element) -> bool:
    """An element is in the FULL build if it has no ``displayOption`` or its
    option token set contains ``full``.  ``concise``-only (and ``concise lite``)
    elements are excluded."""
    if not isinstance(el.tag, str):  # comments / PIs
        return False
    opt = el.get("displayOption")
    if opt is None:
        return True
    return "full" in opt.split()


def apply_full_filter(root: etree._Element) -> None:
    """Hierarchically remove every subtree that is not in the FULL build.

    Done top-down: dropping a ``concise``-only parent also removes its (possibly
    untagged) children, which is exactly how the entire concise-only
    ``<subfields>`` table of a heading field doc disappears in the FULL build.
    """

    def prune(parent: etree._Element) -> None:
        for child in list(parent):
            if isinstance(child.tag, str) and not in_full(child):
                parent.remove(child)
            else:
                prune(child)

    prune(root)


# ---------------------------------------------------------------------------
# Text flattening / normalization
# ---------------------------------------------------------------------------

_DELIMITER = "‡"  # ‡ double dagger = MARC subfield delimiter display form
_PERMILLE = "‰"   # ‰ positional spacer used only in example controlfields
_WS = re.compile(r"\s+")
# Inline markup that occasionally appears ESCAPED as literal text in the source
# (e.g. ad670 "&lt;em&gt;His&lt;/em&gt;"); strip the residual tags.
_INLINE_TAG = re.compile(r"</?(?:em|strong|u|i|b|a)(?:\s[^>]*)?>", re.I)

# Elements whose text must never bleed into a description.
_NON_PROSE = {"examplesec", "examplegp", "example", "history", "marc:datafield",
              "datafield", "controlfield", "subfield_marc"}


def _node_text(el: etree._Element) -> str:
    """Recursively collect visible text, unwrapping inline markup
    (``em``/``strong``/``u``/``a``) and skipping non-prose subtrees."""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        # Recurse only into real prose elements: skip non-prose subtrees and
        # comments / PIs (non-string tag), whose text is editorial scaffolding
        # — e.g. deleted sentences kept as <!-- ... --> in the source.
        if isinstance(child.tag, str) and child.tag.lower() not in _NON_PROSE:
            parts.append(_node_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def flatten_paragraphs(el: etree._Element | None) -> str:
    """Flatten the ``<p>`` children of a ``<description>``/``<definition>`` into
    a single plain-text string."""
    if el is None:
        return ""
    paras = el.findall("p")
    chunks = [_node_text(p) for p in paras] if paras else [_node_text(el)]
    text = "\n\n".join(c.strip() for c in chunks if c.strip())
    return normalize_text(text)


def flatten_descriptions(el: etree._Element) -> str:
    """Concatenate every direct ``<description>`` child of ``el`` (a subfield,
    position, etc.).  Several FULL ``<description>`` siblings can coexist
    (e.g. control subfield ``$8``); they are joined into one description."""
    chunks = [flatten_paragraphs(d) for d in el.findall("description")]
    text = "\n\n".join(c for c in chunks if c)
    return text


def normalize_text(text: str) -> str:
    text = text.replace(_DELIMITER, "$")  # "subfield ‡2" -> "subfield $2"
    text = text.replace(_PERMILLE, "")
    text = _INLINE_TAG.sub("", text)      # strip residual escaped inline markup
    # collapse internal whitespace but preserve paragraph breaks
    text = "\n\n".join(_WS.sub(" ", p).strip() for p in text.split("\n\n"))
    return text.strip()


# ---------------------------------------------------------------------------
# Code / glyph normalization
# ---------------------------------------------------------------------------


def normalize_code(label: str) -> str:
    """Map a MARC code label to its real value: ``#`` -> space; strip spacers."""
    code = (label or "").replace(_PERMILLE, "").strip()
    if code == "#":
        return " "
    return code


# ---------------------------------------------------------------------------
# Repeatability + dates
# ---------------------------------------------------------------------------

_MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def repeatable(text: str | None) -> bool | None:
    if text is None:
        return None
    t = text.strip().upper()
    if t == "R":
        return True
    if t == "NR":
        return False
    return None


def normalize_date(raw: str | None) -> str | None:
    """``dateIssued`` -> Avram timestamp.  Handles ``YYYYMM`` (the norm),
    ``YYYYMMDD`` (``ad455``), ``Month YYYY`` (``ad083``), and the verified
    ``October 200910`` typo (trailing digits after the year are ignored)."""
    if not raw:
        return None
    raw = raw.strip()
    if re.fullmatch(r"\d{6}", raw):
        return f"{raw[:4]}-{raw[4:6]}"
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if re.fullmatch(r"\d{4}", raw):
        return raw
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})\d*", raw)
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(2)}-{_MONTHS[m.group(1).lower()]}"
    return raw or None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def child_text(el: etree._Element, tag: str) -> str | None:
    c = el.find(tag)
    if c is None:
        return None
    txt = normalize_text(_node_text(c))
    return txt or None
