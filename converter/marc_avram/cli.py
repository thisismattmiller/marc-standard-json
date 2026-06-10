"""Command-line entry point.

Default: build every MARC format's full version history into ``--out`` (one
folder per format) plus a clientside diff viewer.  Also supports building a
single schema (``--format`` + ``--as-of`` + ``-o``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import diff, viewer
from .build import build_schema
from .formats import REGISTRY, resolve_source
from .versioning import list_updates


def _strip_internal(schema: dict, keep: bool) -> dict:
    return schema if keep else {k: v for k, v in schema.items() if not k.startswith("_")}


def _validate(schema: dict, metaschema: str, tag: str) -> int:
    from .validate import validate_schema
    errors = validate_schema(schema, metaschema)
    for e in errors[:30]:
        print(f"  INVALID [{tag}] {e}", file=sys.stderr)
    return len(errors)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MARC 21 XML -> Avram schema + diff viewer")
    p.add_argument("source", help="MARCDOCS/XML_files dir (or a single format's dir)")
    p.add_argument("--out", default="versions", help="output root (default: versions/)")
    p.add_argument("--format", action="append",
                   help="format slug(s) to build; repeatable. Default: all present")
    p.add_argument("--as-of", type=int, metavar="N", help="single build at update N")
    p.add_argument("-o", "--output", help="single-build output path (with --format)")
    p.add_argument("--validate", metavar="METASCHEMA", help="validate every snapshot")
    p.add_argument("--updates-html", metavar="HTML",
                   help="LoC 'MARC Format Documentation Overview' page; parsed "
                        "into <out>/updates.json + updates.js for the viewer")
    p.add_argument("--keep-internal", action="store_true")
    p.add_argument("--no-viewer", action="store_true", help="skip writing index.html")
    args = p.parse_args(argv)

    slugs = args.format or list(REGISTRY)

    # single-build mode
    if args.output or args.as_of is not None:
        slug = slugs[0]
        cfg = REGISTRY[slug]
        schema = build_schema(cfg, resolve_source(args.source, cfg), args.as_of)
        out = _strip_internal(schema, args.keep_internal)
        if args.validate:
            _validate(out, args.validate, slug)
        text = json.dumps(out, indent=2, ensure_ascii=False)
        if args.output and args.output != "-":
            Path(args.output).write_text(text + "\n", encoding="utf-8")
            print(f"wrote {args.output} ({len(out['fields'])} fields)", file=sys.stderr)
        else:
            print(text)
        return 0

    # full multi-format / multi-version build
    out_root = Path(args.out)
    built: list[str] = []
    total_invalid = 0
    for slug in slugs:
        cfg = REGISTRY[slug]
        src = resolve_source(args.source, cfg)
        if not list(src.glob(cfg.glob())):
            print(f"[{slug}] no files found, skipping", file=sys.stderr)
            continue
        invalid, last = _build_history(cfg, src, out_root / slug, args)
        total_invalid += invalid
        built.append(slug)
        # newest snapshot under a stable name, in latest/ next to the out root
        latest_dir = out_root.parent / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        (latest_dir / f"{slug}_latest.avram.json").write_text(
            json.dumps(last, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.updates_html:
        from .updates import write_updates
        path = write_updates(args.updates_html, out_root)
        print(f"updates: {path}", file=sys.stderr)
    if built and not args.no_viewer:
        # the viewer lives at the repo root (next to versions/) and fetches
        # data over HTTP, so the tree deploys straight to GitHub Pages
        path = viewer.write_viewer(out_root.parent, built, out_root.name)
        print(f"viewer: {path}", file=sys.stderr)
    if args.validate:
        print(f"total metaschema violations: {total_invalid}", file=sys.stderr)
    return 0


def _build_history(cfg, src, outdir: Path, args) -> tuple[int, dict]:
    """Write one format's full version history; returns ``(invalid_count,
    latest_schema)`` so the caller can publish the newest snapshot."""
    outdir.mkdir(parents=True, exist_ok=True)
    updates = list_updates(src, cfg.glob())
    plan = []  # (cut, id, label, fname)
    if updates:
        base_cut = updates[0] - 1
        plan.append((base_cut, "base", "Base", "update_00_base.avram.json"))
        for n in updates:
            plan.append((n, str(n), f"Update {n}", f"update_{n:02d}.avram.json"))
    else:
        plan.append((None, "base", "Latest", "schema.avram.json"))

    snapshots, invalid = [], 0
    for cut, vid, label, fname in plan:
        schema = build_schema(cfg, src, cut)
        out = _strip_internal(schema, args.keep_internal)
        if vid == "base":
            out["title"] = f"{cfg.title} (base)"
            out["description"] = f"{cfg.title}, earliest captured state."
        if args.validate:
            invalid += _validate(out, args.validate, f"{cfg.slug} {vid}")
        (outdir / fname).write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        snapshots.append({"id": vid, "label": label, "file": fname, "schema": out})

    dataset = diff.build_dataset(cfg.slug, cfg.name, cfg.title, snapshots)
    diff.write_diffs_json(dataset, outdir / "diffs.json")
    (outdir / "manifest.json").write_text(
        json.dumps(dataset["versions"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    last = snapshots[-1]["schema"]
    print(f"[{cfg.slug}] {len(snapshots)} versions, {len(last['fields'])} fields"
          + (f", {invalid} invalid" if args.validate else ""), file=sys.stderr)
    return invalid, last


if __name__ == "__main__":
    raise SystemExit(main())
