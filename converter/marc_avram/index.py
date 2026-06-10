"""Stage 3 — cross-reference indexes built from the non-per-field docs.

Driven by a :class:`~marc_avram.formats.FormatConfig` so it works for every
MARC 21 format:

* X-group ``<fieldGroup>`` docs (``{p}x00`` …) supply the FULL subfields and
  indicators for heading fields, scoped by ``@field``.
* Overlay docs (Authority's ``adtracing``/``ad7xx``) supply field-specific
  overrides and 700's ind2 codelist.
* Appendix ``<part>`` docs (``{p}apndx*``) supply the prose for "See Appendix X"
  subfield pointers, keyed by appendix letter.
* TOC ``<fieldGroup>`` docs supply roster metadata and ``<history>`` lifecycle.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from . import parsers, xmlutil
from .formats import FormatConfig
from .versioning import select_versions

_POINTER = re.compile(r"see\s+(the\s+)?description.*?appendix\s+([a-z])", re.I | re.S)


class Index:
    def __init__(self, cfg: FormatConfig, directory: str | Path,
                 max_update: int | None = None):
        self.cfg = cfg
        self.dir = Path(directory)
        self.max_update = max_update
        self.files = select_versions(self.dir, max_update, cfg.glob())
        self.xgroups: dict[str, etree._Element] = {}
        self.overlays: dict[str, etree._Element] = {}
        self.appendix: dict[str, dict] = {}     # letter -> {code -> {...}}
        self.roster: dict[str, dict] = {}       # tag -> {label, repeatable}
        self.history: dict[str, dict] = {}       # tag -> {status,date,...}
        self._load()

    # -- loading -----------------------------------------------------------
    def _load(self) -> None:
        overlay_stems = self.cfg.overlay_stems()
        shared_stems = {s for s, _ in self.cfg.shared_groups}
        for stem, path in self.files.items():
            if self.cfg.is_xgroup_stem(stem) or stem in shared_stems:
                self.xgroups[stem] = xmlutil.parse(path)
            elif stem in overlay_stems:
                self.overlays[stem] = xmlutil.parse(path)
            elif self.cfg.is_appendix_stem(stem):
                self._load_appendix(stem, path)
        for stem, path in self.files.items():
            self._maybe_load_roster(stem, path)

    def _load_appendix(self, stem: str, path: Path) -> None:
        root = xmlutil.parse(path)
        letter = self.cfg.appendix_letter(stem)
        block = root.find(".//subfields")
        if block is None or letter is None:
            return
        for sf in block.findall("subfield"):
            code = (xmlutil.child_text(sf, "label") or "").strip()
            if not code:
                continue
            # a code may have several entries with different @field scopes
            self.appendix.setdefault(letter, {}).setdefault(code, []).append({
                "description": xmlutil.flatten_descriptions(sf),
                "codes": parsers.parse_value_codes(sf),
                "scope": parsers.parse_field_scope(sf),
            })

    def _maybe_load_roster(self, stem: str, path: Path) -> None:
        root = xmlutil.parse(path)
        if root.tag != "fieldGroup":
            return
        for ref in root.findall(".//fieldtocs/fieldRef"):
            tag = (xmlutil.child_text(ref, "label") or "").strip()
            if not re.fullmatch(r"\d{3}", tag):
                continue
            self.roster.setdefault(tag, {})
            # remember which TOC doc rostered the tag: roster-only fields are
            # documented on that group page (bib 841 -> bd84188x.html)
            self.roster[tag].setdefault("stem", stem)
            if "label" not in self.roster[tag]:
                name = xmlutil.child_text(ref, "name")
                if name:
                    self.roster[tag]["label"] = name
            rep = xmlutil.repeatable(xmlutil.child_text(ref, "repeat"))
            if rep is not None and "repeatable" not in self.roster[tag]:
                self.roster[tag]["repeatable"] = rep
        for fld in root.findall(".//history/field"):
            tag = (xmlutil.child_text(fld, "label") or "").strip()
            status = fld.find("status")
            if not (re.fullmatch(r"\d{3}", tag) and status is not None):
                continue
            rec = {
                "status": (status.text or "").strip(),
                "date": status.get("date"),
                "label": xmlutil.child_text(fld, "name"),
                # <format> children scope a record to a legacy/material
                # format (e.g. 751's OBSOLETE applies to CANMARC only)
                "scoped": fld.find("format") is not None,
            }
            cur = self.history.get(tag)
            # A format-wide record beats a format-scoped one; otherwise the
            # first record encountered wins (as before).
            if cur is None or (cur["scoped"] and not rec["scoped"]):
                self.history[tag] = rec

    # -- queries -----------------------------------------------------------
    def xgroup_for_tag(self, tag: str) -> etree._Element | None:
        stem = self.cfg.xgroup_stem_for_tag(tag)
        if stem and stem in self.xgroups:
            return self.xgroups[stem]
        for shared_stem, pred in self.cfg.shared_groups:
            if pred(tag) and shared_stem in self.xgroups:
                return self.xgroups[shared_stem]
        return None

    def overlay_for_tag(self, tag: str) -> etree._Element | None:
        for stem, pred in self.cfg.overlays:
            if pred(tag) and stem in self.overlays:
                return self.overlays[stem]
        return None

    def resolve_appendix_pointer(self, description: str):
        if not description:
            return None
        m = _POINTER.search(description)
        return m.group(2).lower() if m else None

    def appendix_entry(self, letter: str, code: str, tag: str):
        for entry in self.appendix.get(letter, {}).get(code, []):
            if parsers.scope_match(entry.get("scope"), tag):
                return entry
        return None
