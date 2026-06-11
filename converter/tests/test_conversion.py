"""Regression tests for the MARC 21 Authority -> Avram converter.

Run from the converter/ directory with:  uv run pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marc_avram.build import build_schema, build_format
from marc_avram.formats import REGISTRY
from marc_avram.versioning import select_latest, list_updates
from marc_avram.validate import validate_schema

ROOT = Path(__file__).resolve().parents[2]
XML = ROOT / "MARCDOCS" / "XML_files"
SRC = XML / "Authority"
METASCHEMA = ROOT / "converter" / "avram_schema.yaml"


@pytest.fixture(scope="session")
def schema():
    return build_schema("authority", SRC)


# -- Stage 0: version selection --------------------------------------------

def test_version_selection_is_numeric():
    latest = {k: v.name for k, v in select_latest(SRC).items()}
    assert latest["ad01x09x"] == "ad01x09x_up37.xml"   # not up7/up9
    assert latest["adx00"] == "adx00_up40.xml"
    assert latest["adleader"] == "adleader_up23.xml"
    assert latest["adapndxh"] == "adapndxh_up41.xml"


# -- The proof case: field 100 subfield set --------------------------------

def test_field_100_subfield_set(schema):
    sf = schema["fields"]["100"]["subfields"]
    assert list(sf) == list("abcdefghjklmnopqrstvxyz") + ["6", "7", "8"]
    assert schema["fields"]["100"]["repeatable"] is False
    assert schema["fields"]["100"]["indicator2"] is None
    assert schema["fields"]["100"]["indicator1"]["codes"].keys() >= {"0", "1", "3"}


# -- Heading merge: every heading field gets subfields from its X-group -----

def test_all_heading_fields_have_subfields(schema):
    f = schema["fields"]
    headings = [t for t in f if t[:1] in "1457" and t[1:].isdigit() and len(t) == 3]
    missing = [t for t in headings if "subfields" not in f[t]]
    assert missing == [], f"heading fields missing subfields: {missing}"


def test_700_ind2_from_ad7xx_ind1_inherited(schema):
    f700 = schema["fields"]["700"]
    # ind1 inherited from adx00
    assert f700["indicator1"]["label"].startswith("Type of personal name")
    # ind2 Thesaurus codelist comes from ad7xx
    assert f700["indicator2"]["label"] == "Thesaurus"
    assert "0" in f700["indicator2"]["codes"]


# -- Positional + prose-only control (P0-3/P0-4) ---------------------------

def test_008_positions(schema):
    pos = schema["fields"]["008"]["positions"]
    assert "00-05" in pos and pos["00-05"]["start"] == 0 and pos["00-05"]["end"] == 5
    assert "codes" not in pos["00-05"]          # numeric run, no codelist
    assert " " in pos["06"]["codes"]            # '#' -> space


@pytest.mark.parametrize("tag", ["001", "003", "005"])
def test_control_fields_are_prose_only(schema, tag):
    f = schema["fields"][tag]
    assert "positions" not in f and "subfields" not in f


def test_leader_remapped(schema):
    assert "LDR" in schema["fields"]
    assert "lead" not in schema["fields"]
    assert schema["fields"]["LDR"]["positions"]


# -- Appendix merges (P0-1/P0-5) -------------------------------------------

def test_appendix_subfield_value_codes(schema):
    # $8 field-link-type codes p/u come from Appendix A
    sf8 = schema["fields"]["100"]["subfields"]["8"]
    assert sf8["codes"].keys() >= {"p", "u"}


def test_375_routed_inline_not_missing_xgroup(schema):
    # 375 has full-concise subfields; last-two-digits=75 has no adx75
    sf = schema["fields"]["375"]["subfields"]
    assert set("astuv") <= set(sf)


# -- Whole-schema integrity ------------------------------------------------

def test_metaschema_valid(schema):
    errors = validate_schema(schema, METASCHEMA)
    assert errors == [], "\n".join(errors[:20])


def test_no_flattening_artifacts(schema):
    blob = json.dumps(schema["fields"], ensure_ascii=False)
    for bad in ("‡", "‰", "<em>", "<p>", "displayOption"):
        assert bad not in blob, f"artifact {bad!r} leaked into output"


# -- Versioned snapshots ("as of update N") --------------------------------

def test_list_updates():
    ups = list_updates(SRC)
    assert 14 in ups and 34 in ups and 41 in ups
    assert 29 not in ups and 39 not in ups        # gaps in the update sequence


def test_as_of_models_field_introduction():
    # RDA field 336 was introduced at update 10
    assert "336" not in build_schema("authority", SRC, 9)["fields"]
    assert "336" in build_schema("authority", SRC, 14)["fields"]


def test_as_of_models_subfield_introduction():
    # $7 Data Provenance (Appendix H) is not present before update 34
    assert "7" not in build_schema("authority", SRC, 14)["fields"]["100"]["subfields"]
    assert "7" in build_schema("authority", SRC, 34)["fields"]["100"]["subfields"]


def test_snapshots_grow_monotonically_and_validate():
    counts = []
    for n in (7, 14, 23, 34, 41):
        s = build_schema("authority", SRC, n)
        assert validate_schema(s, METASCHEMA) == []
        counts.append(len(s["fields"]))
    assert counts == sorted(counts)            # field roster never shrinks here


# -- All five formats ------------------------------------------------------

@pytest.mark.parametrize("slug", list(REGISTRY))
def test_every_format_builds_validly(slug):
    s = build_format(slug, XML)
    assert validate_schema(s, METASCHEMA) == []
    f = s["fields"]
    assert "LDR" in f and f["LDR"].get("positions")     # leader resolved
    assert "008" in f                                    # control field present
    assert sum("subfields" in v for v in f.values()) > 5


@pytest.fixture(scope="session")
def bib():
    return build_format("bibliographic", XML)["fields"]


def test_bibliographic_008_material_types_and_headings(bib):
    f = bib
    # 008 keeps its common positions AND gains material variants as `types`
    assert "00-05" in f["008"]["positions"] and "18-34" in f["008"]["positions"]
    assert "Books" in f["008"]["types"]
    assert "positions" in f["008"]["types"]["Books"]
    # heading field 100 sources subfields from the bdx00 X-group
    assert set("abcd") <= set(f["100"]["subfields"])
    assert f["100"]["indicator1"]["label"].startswith("Type of personal name")


def test_grouped_positions_do_not_collapse(bib):
    """Material-specific position layouts must not be merged into one
    overlapping map (006/007 define per-material layouts inline)."""
    # the base maps hold no material-specific entries ...
    assert "positions" not in bib["006"]
    assert "positions" not in bib["007"]
    # ... they live under `types`, one layout per material
    assert "Books" in bib["006"]["types"]
    assert "01-04" in bib["006"]["types"]["Maps"]["positions"]      # Relief
    assert "01-02" in bib["006"]["types"]["Music"]["positions"]     # Form of composition
    # field-level 008 positions contain only the common (All materials) runs
    assert "18-21" not in bib["008"]["positions"]


def test_bib_subfield_i_scoped_to_700_only(bib):
    """bdx00's $i is scoped "[700]" via its name (no @field attribute)."""
    assert "i" not in bib["100"]["subfields"]
    assert "i" not in bib["600"]["subfields"]
    assert "i" not in bib["800"]["subfields"]
    assert bib["700"]["subfields"]["i"]["label"] == "Relationship information"


def test_751_not_deprecated(bib):
    """751's CANMARC-scoped OBSOLETE history record must not flag the
    current MARC 21 field as deprecated."""
    assert "deprecated" not in bib["751"]
    assert bib["440"].get("deprecated") is True   # genuinely obsolete


def test_tracing_w_positions_and_i_repeatability(schema):
    """Overlay merge keeps adtracing's $w position table; the X-group's
    repeatability wins over the overlay (published docs show $i as R)."""
    w = schema["fields"]["447"]["subfields"]["w"]
    assert {"0", "1", "2", "3"} <= set(w["positions"])
    assert schema["fields"]["447"]["subfields"]["i"]["repeatable"] is True
    assert schema["fields"]["747"]["subfields"]["i"]["repeatable"] is True


def test_field_urls_follow_loc_page_naming(schema, bib):
    """URLs mirror the source doc stem: per-field docs get their own page,
    leaders get <prefix>leader.html, roster-only fields their group page."""
    assert bib["LDR"]["url"].endswith("/bdleader.html")
    assert schema["fields"]["LDR"]["url"].endswith("/adleader.html")
    assert bib["100"]["url"].endswith("/bd100.html")
    # 841-88X holdings-format fields have no bd841.html page of their own
    assert bib["841"]["url"].endswith("/bd84188x.html")
    assert bib["853"]["url"].endswith("/bd84188x.html")
    assert bib["900"]["url"].endswith("/bd9xx.html")
    # duplicate doc exports lose ties to the canonically-named doc
    ci = build_format("community", XML)["fields"]
    assert ci["008"]["url"].endswith("/ci008.html")


def test_field_scope_exclusions_and_ranges():
    from lxml import etree
    from marc_avram import parsers
    ex = etree.fromstring(
        '<subfield field="[all except 533, 760-788, 800-830, and 856]"/>')
    assert parsers.in_scope(ex, "650")
    assert not parsers.in_scope(ex, "773")      # inside an excluded range
    assert not parsers.in_scope(ex, "810")
    assert not parsers.in_scope(ex, "533")
    inc = etree.fromstring('<subfield field="[760-788 only]"/>')
    assert parsers.in_scope(inc, "773") and not parsers.in_scope(inc, "300")


def test_appendix_splice_respects_exclusion_scope():
    # Appendix H $7 was scoped "[all except 856 and 857]" at update 36-40:
    # 750 must get the spliced prose, 856 must keep its own definition.
    f = build_schema("authority", SRC, 40)["fields"]
    assert f["750"]["subfields"]["7"]["description"].startswith(
        "Subfield $7 contains a data provenance value")
    assert not f["856"]["subfields"]["7"]["description"].startswith(
        "Subfield $7 contains")


def test_shared_group_subfields(bib):
    """Linking fields (bib 760-787) and holdings 853-878 source their FULL
    subfields from their General Information docs (bd760787, hd853855...)."""
    assert set("abst") <= set(bib["773"]["subfields"])
    assert bib["773"]["subfields"]["7"]["label"] == "Control subfield"
    # range-scoped appendix splice: $y "[533 and 800-830 only]" covers 810
    assert bib["810"]["subfields"]["y"]["description"].startswith("Subfield $y")
    hold = build_format("holdings", XML)["fields"]
    for t in ("853", "863", "866", "876"):
        assert hold[t].get("subfields"), f"holdings {t} has no subfields"


def test_diff_hunks_carry_json_path_context():
    from marc_avram.diff import _unified
    old = {"tag": "100", "subfields": {"7": {"label": "Data provenance",
                                             "description": "old text"}}}
    new = {"tag": "100", "subfields": {"7": {"label": "Data provenance",
                                             "description": "new text"}}}
    hunks = [t for m, t in _unified(old, new) if m == "@"]
    assert hunks and hunks[0].endswith("subfields › $7")


def test_updates_overview_parses():
    from marc_avram.updates import parse_overview
    src = next((ROOT / "MARC_HTML").glob("MARC Format Documentation Overview*"))
    data = parse_overview(src.read_text(encoding="utf-8", errors="replace"))
    assert set(data) == {"bibliographic", "authority", "holdings",
                         "classification", "community"}
    bib = data["bibliographic"]
    assert bib["base"]["url"].endswith("/marc/bibbas99.html")
    assert bib["13"]["url"].endswith("up13bibliographic/bdapndxg.html")
    # combined "Update No. 10 ... and Update No. 11" entry covers both
    assert bib["10"]["url"] == bib["11"]["url"]
    assert data["authority"]["8"]["url"].endswith("up8authority/adapndxf.html")


def test_no_comment_text_leaks(schema, bib):
    """XML comment bodies (editorial notes, deleted prose) must not bleed
    into descriptions."""
    for fields in (schema["fields"], bib):
        blob = json.dumps(fields, ensure_ascii=False)
        for bad in ("&#x", "WS: Added link", "may be omitted if the number equals 1"):
            assert bad not in blob, f"comment text {bad!r} leaked into output"
