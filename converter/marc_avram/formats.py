"""Per-format configuration.

The five MARC 21 formats share the same publishing-XML conventions but use
different filename prefixes (``ad``/``bd``/``hd``/``cd``/``ci``) and live in
different documentation paths.  Everything else (X-group stems, appendix stems,
leader label, control-field variants) is derived generically from the prefix
plus structural cues, so adding a format is just a registry entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class FormatConfig:
    slug: str               # output dir name, e.g. "authority"
    name: str               # human name, e.g. "Authority"
    title: str              # Avram schema title
    marc_path: str          # loc.gov/marc/<marc_path>/
    prefix: str             # filename prefix: ad, bd, hd, cd, ci
    dirname: str            # XML subdirectory under MARCDOCS/XML_files/
    # overlay docs: (stem, predicate(tag)) supplying field-specific overrides
    overlays: list[tuple[str, Callable[[str], bool]]] = field(default_factory=list)

    # -- derived helpers ---------------------------------------------------
    def glob(self) -> str:
        return f"{self.prefix}*.xml"

    def is_xgroup_stem(self, stem: str) -> bool:
        return bool(re.fullmatch(rf"{self.prefix}x\d\d", stem))

    def xgroup_stem_for_tag(self, tag: str) -> str | None:
        if len(tag) == 3 and tag.isdigit():
            return f"{self.prefix}x{tag[1:]}"
        return None

    def is_appendix_stem(self, stem: str) -> bool:
        return bool(re.fullmatch(rf"{self.prefix}apndx[a-z]", stem))

    def appendix_letter(self, stem: str) -> str | None:
        m = re.fullmatch(rf"{self.prefix}apndx([a-z])", stem)
        return m.group(1) if m else None

    def overlay_stems(self) -> set[str]:
        return {s for s, _ in self.overlays}

    def control_variant(self, stem: str) -> tuple[str, str] | None:
        """A material/character-position variant of a control field, e.g.
        ``bd008b`` -> ("008", "b"), ``bd007a`` -> ("007", "a").  Returns
        ``(base_tag, variant_key)`` or ``None``."""
        m = re.fullmatch(rf"{self.prefix}(00[678])([a-z][a-z0-9]*)", stem)
        if m:
            return m.group(1), m.group(2)
        return None

    def field_slug(self, tag: str) -> str:
        # loc.gov leader pages are prefixed: bdleader.html, cdleader.html, ...
        return f"{self.prefix}leader" if tag == "LDR" else f"{self.prefix}{tag.lower()}"

    def field_url(self, tag: str) -> str:
        return f"https://www.loc.gov/marc/{self.marc_path}/{self.field_slug(tag)}.html"

    def doc_url(self, stem: str) -> str:
        # published pages are all-lowercase (the XML has stems like cd76X)
        return f"https://www.loc.gov/marc/{self.marc_path}/{stem.lower()}.html"


def _starts(prefixes: str) -> Callable[[str], bool]:
    return lambda t: bool(t) and t[0] in prefixes


REGISTRY: dict[str, FormatConfig] = {
    "authority": FormatConfig(
        slug="authority", name="Authority",
        title="MARC 21 Format for Authority Data",
        marc_path="authority", prefix="ad", dirname="Authority",
        overlays=[("adtracing", _starts("45")), ("ad7xx", _starts("7"))],
    ),
    "bibliographic": FormatConfig(
        slug="bibliographic", name="Bibliographic",
        title="MARC 21 Format for Bibliographic Data",
        marc_path="bibliographic", prefix="bd", dirname="Bibliographic",
    ),
    "holdings": FormatConfig(
        slug="holdings", name="Holdings",
        title="MARC 21 Format for Holdings Data",
        marc_path="holdings", prefix="hd", dirname="Holdings",
    ),
    "classification": FormatConfig(
        slug="classification", name="Classification",
        title="MARC 21 Format for Classification Data",
        marc_path="classification", prefix="cd", dirname="Classification",
    ),
    "community": FormatConfig(
        slug="community", name="Community Information",
        title="MARC 21 Format for Community Information",
        marc_path="community", prefix="ci", dirname="Community Information",
    ),
}


def resolve_source(base_dir: str | Path, cfg: FormatConfig) -> Path:
    """Locate the XML directory for a format under an ``XML_files`` root, or
    accept a directory that already points straight at the files."""
    base = Path(base_dir)
    cand = base / cfg.dirname
    if cand.is_dir():
        return cand
    return base
