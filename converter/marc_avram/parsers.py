"""Shared parsers for the structural building blocks: subfields, indicators,
and character positions.  Reused by both inline-variable field extraction and
the X-group / appendix index.

All input elements are assumed to have already passed the FULL filter.
"""

from __future__ import annotations

import re

from lxml import etree

from . import xmlutil

_TAG3 = re.compile(r"\d{3}")
_TAG_RANGE = re.compile(r"(\d{3})(?:\s*-\s*(\d{3}))?")
_EXCEPT = re.compile(r"\bexcept\b", re.I)

# Scope expressed only in the display name, e.g. bdx00's $i
# "Relationship information [700]" (the lone definition with no @field).
_NAME_SCOPE = re.compile(r"\s*\[(\d{3}(?:/\d{3})*)/?\]$")


def _expand_tags(raw: str) -> set[str]:
    """All tags in ``raw``, expanding ``760-788``-style ranges."""
    tags: set[str] = set()
    for a, b in _TAG_RANGE.findall(raw):
        if b:
            tags.update(f"{n:03d}" for n in range(int(a), int(b) + 1))
        else:
            tags.add(a)
    return tags


def parse_field_scope(el: etree._Element):
    """Parse a ``field`` scope attribute.

    Returns ``None`` (applies to every member), a tag set for inclusion
    scopes (``"[400/500/700]"``, ``"[856 and 857 only]"``, ``"[760-788
    only]"`` — ranges are expanded), or ``("except", tags)`` for exclusion
    scopes (``"[all except 856 and 857]"``).  Tolerates the verified
    ``adx11`` typo ``[411/511/711/]``.  When the attribute is absent, falls
    back to a trailing ``[700]``-style tag list in ``<name>``."""
    raw = el.get("field")
    if raw is not None:
        tags = _expand_tags(raw)
        if not tags:
            return None
        return ("except", tags) if _EXCEPT.search(raw) else tags
    name = xmlutil.child_text(el, "name")
    if name:
        m = _NAME_SCOPE.search(name)
        if m:
            return set(m.group(1).split("/"))
    return None


def scope_match(scope, tag: str) -> bool:
    if scope is None:
        return True
    if isinstance(scope, tuple):       # ("except", tags)
        return tag not in scope[1]
    return tag in scope


def in_scope(el: etree._Element, tag: str) -> bool:
    return scope_match(parse_field_scope(el), tag)


_SKIP_ANCESTORS = {"history", "examplesec", "examplegp", "example"}


def find_block(container: etree._Element, name: str) -> etree._Element | None:
    """Find the active ``<subfields>``/``<indicators>``/``<characterPositions>``
    block.  Different formats wrap these in ``<guidelines>`` or ``<fieldpros>``
    (or place them directly), so we take the first matching descendant that is
    not inside a ``<history>`` or example subtree."""
    for el in container.iter(name):
        if el is container:
            continue
        anc = el.getparent()
        skip = False
        while anc is not None and anc is not container:
            if isinstance(anc.tag, str) and anc.tag in _SKIP_ANCESTORS:
                skip = True
                break
            anc = anc.getparent()
        if not skip:
            return el
    return None


# ---------------------------------------------------------------------------
# Subfields
# ---------------------------------------------------------------------------


def parse_value_codes(el: etree._Element) -> dict | None:
    """Parse ``<value>`` children (used by subfields like ``$8`` p/u and by
    indicators) into an Avram codelist."""
    codes: dict[str, dict] = {}
    for v in el.findall("value"):
        code = xmlutil.normalize_code(xmlutil.child_text(v, "label") or "")
        if code == "":
            continue
        entry: dict = {}
        name = xmlutil.child_text(v, "name")
        if name:
            entry["label"] = name
        desc = xmlutil.flatten_descriptions(v)
        if desc:
            entry["description"] = desc
        codes[code] = entry
    return codes or None


def parse_subfield(sf: etree._Element) -> dict:
    """Parse one ``<subfield>`` into an Avram subfield definition (sans code key,
    which the caller uses as the dict key)."""
    code = (xmlutil.child_text(sf, "label") or "").strip()
    out: dict = {"code": code}
    name = xmlutil.child_text(sf, "name")
    if name:
        # drop a trailing "[700]"-style scope annotation from the label
        out["label"] = _NAME_SCOPE.sub("", name).strip()
    rep = xmlutil.repeatable(xmlutil.child_text(sf, "repeat"))
    if rep is not None:
        out["repeatable"] = rep
    desc = xmlutil.flatten_descriptions(sf)
    if desc:
        out["description"] = desc
    group = sf.get("group")
    if group:
        out["categories"] = [group]  # native Avram key (was @group)
    codes = parse_value_codes(sf)
    if codes:
        out["codes"] = codes
    positions = parse_character_positions(sf)
    if positions:
        out["positions"] = positions
    return out


def parse_subfields(container: etree._Element, tag: str | None = None) -> dict:
    """Parse a ``<subfields>`` block into ``{code: definition}``.

    When ``tag`` is given, subfields scoped to other fields (via ``@field``)
    are skipped."""
    out: dict[str, dict] = {}
    block = find_block(container, "subfields")
    if block is None:
        return out
    for sf in block.findall("subfield"):
        if tag is not None and not in_scope(sf, tag):
            continue
        defn = parse_subfield(sf)
        code = defn["code"]
        if code:
            out[code] = defn
    return out


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def parse_indicator(ind: etree._Element):
    """Parse one ``<indicator>`` into an Avram indicator definition, or ``None``
    when it is an "Undefined" indicator with no real codes (Avram null
    placeholder)."""
    codes = parse_value_codes(ind)
    name = xmlutil.child_text(ind, "name")
    # An indicator with no coded values is "Undefined" -> Avram null.
    if not codes:
        return None
    out: dict = {}
    if name:
        out["label"] = name
    desc = xmlutil.flatten_descriptions(ind)
    if desc:
        out["description"] = desc
    out["codes"] = codes
    return out


def parse_indicators(container: etree._Element, tag: str | None = None) -> dict:
    """Return ``{"indicator1": def|None, "indicator2": def|None}`` for any
    indicators defined under ``container``.  Missing indicators are omitted from
    the dict so callers can tell "undefined" (None) from "not specified here".

    When ``tag`` is given, indicators scoped to other fields (via ``@field``,
    as in the up10/up11-era ``bdx10`` docs) are skipped."""
    out: dict = {}
    block = find_block(container, "indicators")
    if block is None:
        return out
    for ind in block.findall("indicator"):
        if tag is not None and not in_scope(ind, tag):
            continue
        label = (xmlutil.child_text(ind, "label") or "").strip().lower()
        if label in ("ind1", "1"):
            out["indicator1"] = parse_indicator(ind)
        elif label in ("ind2", "2"):
            out["indicator2"] = parse_indicator(ind)
    return out


# ---------------------------------------------------------------------------
# Character positions (008, Leader, and control subfields like $w)
# ---------------------------------------------------------------------------

_RANGE = re.compile(r"^/?(\d+)(?:-(\d+))?$")


def _position_key(label: str) -> tuple[str, int, int] | None:
    """``"00-05"`` -> ("00-05", 0, 5); ``"06"`` -> ("06", 6, 6);
    ``"/0"`` (control subfield) -> ("0", 0, 0)."""
    label = (label or "").strip()
    m = _RANGE.match(label)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    key = label.lstrip("/")
    return key, start, end


def _iter_positions(container: etree._Element):
    block = find_block(container, "characterPositions")
    return (block.findall("characterPosition") if block is not None
            else container.findall("characterPosition"))


def _parse_position(cp: etree._Element) -> tuple[str, dict] | None:
    parsed = _position_key(xmlutil.child_text(cp, "label") or "")
    if not parsed:
        return None
    key, start, end = parsed
    entry: dict = {"start": start, "end": end}
    name = xmlutil.child_text(cp, "name")
    if name:
        entry["label"] = name
    desc = xmlutil.flatten_descriptions(cp)
    if desc:
        entry["description"] = desc
    codes = parse_value_codes(cp)
    if codes:
        entry["codes"] = codes
    return key, entry


def parse_character_positions(container: etree._Element) -> dict:
    """Ungrouped positions only.  Material-specific positions (tagged with a
    ``group`` attribute, e.g. ``bd006``'s per-material layouts) overlap each
    other and must not be merged into one map — they are collected separately
    by :func:`parse_grouped_positions`."""
    out: dict[str, dict] = {}
    for cp in _iter_positions(container):
        if cp.get("group"):
            continue
        kv = _parse_position(cp)
        if kv:
            out[kv[0]] = kv[1]
    return out


def parse_grouped_positions(container: etree._Element) -> dict[str, dict]:
    """``{material group: {position: definition}}`` for ``group``-attributed
    positions (``bd006``/``bd007``/``bd008``/``hd007``)."""
    out: dict[str, dict] = {}
    for cp in _iter_positions(container):
        group = cp.get("group")
        if not group:
            continue
        kv = _parse_position(cp)
        if kv:
            out.setdefault(group.strip(), {})[kv[0]] = kv[1]
    return out
