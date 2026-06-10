"""Stage 4 & 5 — per-field extraction, dispatched by STRUCTURE (not tag number)
and merged with the X-group / overlay / appendix indexes.
"""

from __future__ import annotations

from lxml import etree

from . import parsers, xmlutil
from .index import Index


def _base_metadata(root: etree._Element, tag: str, index: Index) -> dict:
    out: dict = {"tag": tag}
    label = xmlutil.child_text(root, "name") or index.roster.get(tag, {}).get("label")
    if label:
        out["label"] = label
    rep = xmlutil.repeatable(xmlutil.child_text(root, "repeat"))
    if rep is None:
        rep = index.roster.get(tag, {}).get("repeatable")
    if rep is not None:
        out["repeatable"] = rep
    out["url"] = index.cfg.field_url(tag)
    modified = xmlutil.normalize_date(xmlutil.child_text(root, "dateIssued"))
    if modified:
        out["modified"] = modified
    definition = root.find("definition")
    if definition is not None:
        desc = xmlutil.flatten_descriptions(definition)
        if desc:
            out["description"] = desc
    return out


def _apply_history(defn: dict, tag: str, index: Index) -> None:
    hist = index.history.get(tag)
    if not hist:
        return
    status = (hist.get("status") or "").upper()
    date = hist.get("date")
    if status == "OBSOLETE":
        defn["deprecated"] = True
    elif status == "NEW" and date and "created" not in defn:
        defn["created"] = date
    elif status in ("CHANGED", "REDEFINED", "RENAMED", "REDESCRIBED") and date:
        defn.setdefault("modified", date)


# ---------------------------------------------------------------------------
# Appendix pointer resolution for a subfield
# ---------------------------------------------------------------------------


def _resolve_appendix(sub: dict, tag: str, index: Index) -> None:
    letter = index.resolve_appendix_pointer(sub.get("description", ""))
    if not letter:
        return
    entry = index.appendix_entry(letter, sub["code"], tag)
    if entry is None:
        return
    if entry.get("description"):
        sub["description"] = entry["description"]
    if entry.get("codes") and "codes" not in sub:
        sub["codes"] = entry["codes"]


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def extract_positional(root: etree._Element, tag: str, index: Index) -> dict:
    defn = _base_metadata(root, tag, index)
    positions = parsers.parse_character_positions(root)
    groups = parsers.parse_grouped_positions(root)
    # bd008's "All materials" group holds the positions common to every
    # record — those are field-level, not a material variant.
    for name in list(groups):
        if name.lower() == "all materials":
            positions.update(groups.pop(name))
    if positions:
        defn["positions"] = positions
    # Inline material-specific layouts (bd006, bd007, bd008, hd007) become
    # Avram `types`; richer standalone variant docs replace these in build.
    if groups:
        defn["types"] = {name: {"label": name, "positions": pos}
                         for name, pos in sorted(groups.items())}
    _apply_history(defn, tag, index)
    return defn


def _merge_indicators(inline: dict, xgroup_inds: dict, overlay_inds: dict) -> dict:
    """Per-indicator precedence: inline (per-field doc) > X-group > overlay.
    An overlay's coded ind2 (e.g. Authority 700 Thesaurus) replaces a prose-only
    (``None``) ind2 inherited from the X-group."""
    out: dict = {}
    for k in ("indicator1", "indicator2"):
        if k in inline:
            out[k] = inline[k]
        elif k in xgroup_inds:
            out[k] = xgroup_inds[k]
        if overlay_inds.get(k) is not None and out.get(k) is None:
            out[k] = overlay_inds[k]
    return out


def extract_variable(root: etree._Element, tag: str, index: Index,
                     inline_subs: dict, inline_inds: dict) -> dict:
    """A variable (subfielded) field.  Subfields come inline when the per-field
    doc carries them in the FULL build; otherwise from the X-group (heading
    fields), layered with overlay + appendix prose."""
    defn = _base_metadata(root, tag, index)
    xgroup = index.xgroup_for_tag(tag)
    overlay = index.overlay_for_tag(tag)

    xgroup_inds = parsers.parse_indicators(xgroup, tag) if xgroup is not None else {}
    overlay_inds = parsers.parse_indicators(overlay, tag) if overlay is not None else {}
    _set_indicators(defn, _merge_indicators(inline_inds, xgroup_inds, overlay_inds))

    if inline_subs:
        subs = inline_subs
    else:
        subs = parsers.parse_subfields(xgroup, tag) if xgroup is not None else {}
        if overlay is not None:
            for code, ov in parsers.parse_subfields(overlay, tag).items():
                if code in subs:
                    # The overlay supplies prose and structure the X-group
                    # defers to ($w positions/codes), but the X-group's own
                    # repeatability wins on conflict — it is what the
                    # published per-field pages render (e.g. $i is R, not
                    # adtracing's NR).
                    cur = subs[code]
                    if "repeatable" in ov and "repeatable" not in cur:
                        cur["repeatable"] = ov["repeatable"]
                    if ov.get("description"):
                        cur["description"] = ov["description"]
                    if ov.get("codes") and "codes" not in cur:
                        cur["codes"] = ov["codes"]
                    if ov.get("positions") and "positions" not in cur:
                        cur["positions"] = ov["positions"]
                else:
                    subs[code] = ov
    for sub in subs.values():
        _resolve_appendix(sub, tag, index)
    if subs:
        defn["subfields"] = subs
    _apply_history(defn, tag, index)
    return defn


def extract_prose_control(root: etree._Element, tag: str, index: Index) -> dict:
    defn = _base_metadata(root, tag, index)
    _apply_history(defn, tag, index)
    return defn


def extract_type_variant(root: etree._Element, stem: str, index: Index) -> dict:
    """A ``<fieldCharPosition>`` doc (e.g. ``bd008b`` "Books") -> an Avram typed
    field definition (``positions`` keyed material variant of a control field)."""
    out: dict = {}
    name = xmlutil.child_text(root, "name")
    if name:
        out["label"] = name
    out["url"] = index.cfg.doc_url(stem)
    positions = parsers.parse_character_positions(root)
    if positions:
        out["positions"] = positions
    return out


def _set_indicators(defn: dict, inds: dict) -> None:
    """Emit indicator1/indicator2 only for variable fields.  An explicit ``None``
    (undefined indicator) is preserved as Avram null."""
    if "indicator1" in inds:
        defn["indicator1"] = inds["indicator1"]
    if "indicator2" in inds:
        defn["indicator2"] = inds["indicator2"]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def extract(root: etree._Element, tag: str, index: Index) -> dict:
    """Route a per-field ``<field>`` doc to the right extractor by structure.

    Decided by what survives the FULL filter:
    * active character positions -> positional field;
    * else inline subfields, or an X-group for the tag -> variable field
      (inline subfields win; otherwise the X-group supplies them);
    * else -> prose-only control field.
    """
    if parsers.find_block(root, "characterPositions") is not None:
        return extract_positional(root, tag, index)

    inline_subs = parsers.parse_subfields(root, tag)
    inline_inds = parsers.parse_indicators(root, tag)

    if inline_subs or index.xgroup_for_tag(tag) is not None:
        return extract_variable(root, tag, index, inline_subs, inline_inds)

    return extract_prose_control(root, tag, index)
