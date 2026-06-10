"""Stage 6 — assemble a full Avram schema from all per-field docs + indexes."""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from . import extract, xmlutil
from .formats import FormatConfig, REGISTRY, resolve_source
from .index import Index

_TAG_RE = re.compile(r"^\d{3}$")


def _doc_tag(root: etree._Element) -> str | None:
    """The MARC tag a ``<field>`` doc defines, or ``None`` for group headers."""
    label = (xmlutil.child_text(root, "label") or "").strip()
    if label.lower() == "lead":
        return "LDR"
    if _TAG_RE.fullmatch(label):
        return label
    return None


def _sort_key(tag: str) -> tuple[int, str]:
    return (0, "") if tag == "LDR" else (1, tag)


def build_schema(cfg: FormatConfig | str, directory: str | Path,
                 max_update: int | None = None) -> dict:
    if isinstance(cfg, str):
        cfg = REGISTRY[cfg]
    directory = Path(directory)
    index = Index(cfg, directory, max_update)

    fields: dict[str, dict] = {}
    field_stem: dict[str, str] = {}        # tag -> stem of the doc that won
    type_variants: dict[str, dict] = {}    # base tag -> {type_key: typed_def}
    skipped: list[str] = []

    def canonical(stem: str, tag: str) -> bool:
        return stem.lower() == cfg.field_slug(tag)
    for stem, path in index.files.items():
        root = xmlutil.parse(path)
        if root.tag == "fieldCharPosition":
            base = (xmlutil.child_text(root, "label") or "").strip()
            if _TAG_RE.fullmatch(base):
                typed = extract.extract_type_variant(root, stem, index)
                key = typed.get("label") or (cfg.control_variant(stem) or ("", stem))[1]
                type_variants.setdefault(base, {})[key] = typed
            continue
        # field docs are <field> or, for some leaders, <part>; appendix <part>
        # docs are consumed by the Index, not emitted as fields.
        if root.tag not in ("field", "part") or cfg.is_appendix_stem(stem):
            continue
        tag = _doc_tag(root)
        if tag is None:
            if root.tag == "field":
                skipped.append(stem)
            continue
        defn = extract.extract(root, tag, index)
        # the published page mirrors the source doc: bd100 -> bd100.html,
        # bdleader -> bdleader.html
        defn["url"] = cfg.doc_url(stem)
        cur = fields.get(tag)
        if cur is None:
            take = True
        else:
            new_m, cur_m = defn.get("modified", ""), cur.get("modified", "")
            # newer doc wins; on a tie the canonically-named doc wins
            # (ci008 over its duplicate export ci008_percent)
            take = new_m > cur_m or (
                new_m == cur_m
                and canonical(stem, tag) and not canonical(field_stem[tag], tag))
        if take:
            fields[tag] = defn
            field_stem[tag] = stem

    # attach control-field material variants as Avram `types`
    for base, variants in type_variants.items():
        if base in fields and variants:
            fields[base]["types"] = dict(sorted(variants.items()))

    # roster-only tags (in a TOC but with no standalone doc): minimal stubs
    for tag, meta in index.roster.items():
        if tag in fields:
            continue
        if index.history.get(tag, {}).get("status", "").upper() == "OBSOLETE":
            continue
        # roster-only fields have no page of their own; link the TOC/group
        # page that listed them (e.g. bib 841 -> bd84188x.html)
        url = cfg.doc_url(meta["stem"]) if meta.get("stem") else cfg.field_url(tag)
        stub: dict = {"tag": tag, "url": url}
        if meta.get("label"):
            stub["label"] = meta["label"]
        if "repeatable" in meta:
            stub["repeatable"] = meta["repeatable"]
        fields[tag] = stub

    ordered = {t: fields[t] for t in sorted(fields, key=_sort_key)}
    latest = max((f.get("modified", "") for f in ordered.values()), default="")

    as_of = f" as of Update No. {max_update}" if max_update is not None else ""
    schema: dict = {
        "$schema": "https://format.gbv.de/schema/avram/schema.json",
        "title": f"{cfg.title}{as_of}",
        "description": f"{cfg.title}, derived from the "
                       f"Library of Congress documentation{as_of}.",
        "url": f"https://www.loc.gov/marc/{cfg.marc_path}/",
        "family": "marc",
        "language": "en",
    }
    if latest:
        schema["modified"] = latest
    schema["fields"] = ordered
    schema["_skipped_docs"] = sorted(skipped)
    schema["_update"] = max_update
    return schema


def build_format(slug: str, base_dir: str | Path, max_update: int | None = None) -> dict:
    cfg = REGISTRY[slug]
    return build_schema(cfg, resolve_source(base_dir, cfg), max_update)
