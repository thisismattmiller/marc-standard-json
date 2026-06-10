"""Compute a git-diff-style change timeline between consecutive schema versions
and emit it as a ``diffs.json`` data file for the clientside viewer.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path


def _pretty(field: dict) -> list[str]:
    return json.dumps(field, indent=2, ensure_ascii=False).split("\n")


def _all_lines(field: dict, marker: str) -> list[list[str]]:
    return [[marker, ln] for ln in _pretty(field)]


def _unified(old: dict, new: dict) -> list[list[str]]:
    """Unified-diff lines as ``[marker, text]`` (markers: ' ', '+', '-', '@')."""
    a, b = _pretty(old), _pretty(new)
    out: list[list[str]] = []
    for ln in difflib.unified_diff(a, b, n=2, lineterm=""):
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("@@"):
            out.append(["@", ln])
        elif ln.startswith("+"):
            out.append(["+", ln[1:]])
        elif ln.startswith("-"):
            out.append(["-", ln[1:]])
        else:
            out.append([" ", ln[1:] if ln.startswith(" ") else ln])
    return out


def diff_fields(old: dict, new: dict) -> list[dict]:
    """Per-field changes between two ``fields`` objects, sorted by tag."""
    files: list[dict] = []
    old_tags, new_tags = set(old), set(new)
    for tag in sorted(new_tags - old_tags):
        files.append({"tag": tag, "status": "added", "lines": _all_lines(new[tag], "+")})
    for tag in sorted(old_tags - new_tags):
        files.append({"tag": tag, "status": "removed", "lines": _all_lines(old[tag], "-")})
    for tag in sorted(old_tags & new_tags):
        if old[tag] != new[tag]:
            files.append({"tag": tag, "status": "modified", "lines": _unified(old[tag], new[tag])})
    return files


def build_dataset(slug: str, name: str, title: str,
                  snapshots: list[dict]) -> dict:
    """``snapshots`` = ordered list of ``{id,label,file,modified,schema}``."""
    versions = [{"id": s["id"], "label": s["label"], "file": s["file"],
                 "fields": len(s["schema"].get("fields", {})),
                 "modified": s["schema"].get("modified")} for s in snapshots]
    steps = []
    for prev, cur in zip(snapshots, snapshots[1:]):
        files = diff_fields(prev["schema"].get("fields", {}),
                            cur["schema"].get("fields", {}))
        steps.append({
            "from": prev["id"], "to": cur["id"],
            "fromLabel": prev["label"], "toLabel": cur["label"],
            "date": cur["schema"].get("modified"),
            "added": sum(f["status"] == "added" for f in files),
            "removed": sum(f["status"] == "removed" for f in files),
            "modified": sum(f["status"] == "modified" for f in files),
            "files": files,
        })
    return {"format": slug, "name": name, "title": title,
            "versions": versions, "steps": steps}


def write_diffs_json(dataset: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(dataset, ensure_ascii=False) + "\n",
                          encoding="utf-8")
