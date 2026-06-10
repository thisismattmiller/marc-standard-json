"""Stage 0 — version selection.

Each logical doc exists as ``<stem>_base.xml`` plus zero or more
``<stem>_upNN.xml`` updates.  The authoritative copy is the one with the
numerically highest ``up`` number, falling back to ``_base`` when no update
exists.  Lexical sorting is wrong (``up7`` would beat ``up40``), so the number
is parsed as an integer with ``_base`` treated as ``-1``.
"""

from __future__ import annotations

import re
from pathlib import Path

# adNNN_base.xml / adNNN_upNN.xml ; also adxNN, adapndxX, adleader, ad01x09x ...
_PAT = re.compile(r"^(?P<stem>.+?)(?:_up(?P<n>\d+)|_base)\.xml$")

# Files to ignore even though they end in .xml
_SKIP_SUFFIXES = (".fo.xml",)


def _is_skippable(name: str) -> bool:
    return any(name.endswith(s) for s in _SKIP_SUFFIXES)


def _stem_version(path: Path) -> tuple[str, int]:
    """``(stem, version)`` where ``_base`` -> -1, ``_upNN`` -> NN."""
    m = _PAT.match(path.name)
    if not m:
        return path.stem, -2  # files without _base/_up (rare)
    stem = m.group("stem")
    version = int(m.group("n")) if m.group("n") else -1
    return stem, version


def select_versions(directory: str | Path, max_update: int | None = None,
                    glob: str = "*.xml") -> dict[str, Path]:
    """Return ``{stem: path}`` for the state of every logical doc *as of* update
    ``max_update`` (inclusive).  For each stem the chosen file is the highest
    ``up`` number ``<= max_update``, falling back to ``_base``.  A doc whose
    earliest version is later than ``max_update`` (and has no ``_base``) is
    omitted entirely — modelling fields introduced over time.

    ``max_update=None`` selects the latest version of every doc.  ``glob``
    scopes the scan to one format's prefix (e.g. ``bd*.xml``).
    """
    directory = Path(directory)
    best: dict[str, tuple[int, Path]] = {}
    for path in directory.glob(glob):
        if _is_skippable(path.name):
            continue
        stem, version = _stem_version(path)
        if max_update is not None and version > max_update:
            continue
        if stem not in best or version > best[stem][0]:
            best[stem] = (version, path)
    return {stem: path for stem, (_, path) in best.items()}


def select_latest(directory: str | Path, glob: str = "*.xml") -> dict[str, Path]:
    """Latest version of every logical doc (alias for ``select_versions(...)``)."""
    return select_versions(directory, None, glob)


def list_updates(directory: str | Path, glob: str = "*.xml") -> list[int]:
    """Sorted distinct ``up`` numbers that appear in the directory."""
    directory = Path(directory)
    nums = set()
    for path in directory.glob(glob):
        if _is_skippable(path.name):
            continue
        _, version = _stem_version(path)
        if version >= 0:
            nums.add(version)
    return sorted(nums)
