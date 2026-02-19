"""Regression tests for PDF publish_date behavior."""

from src.pdf_extract import extract_pdf_publish_date_hint
from src.postprocess import postprocess_record


def _base_record(**overrides):
    rec = {
        "title": "Toyota Argentina update",
        "source_type": "Other",
        "publish_date": "2026-02-04",
        "publish_date_confidence": "High",
        "original_url": None,
        "actor_type": "oem",
        "government_entities": [],
        "companies_mentioned": ["Toyota"],
        "mentions_our_company": False,
        "topics": ["OEM Programs & Vehicle Platforms"],
        "keywords": ["toyota", "argentina", "release", "production", "platform"],
        "country_mentions": ["Argentina"],
        "regions_mentioned": [],
        "regions_relevant_to_apex_mobility": [],
        "evidence_bullets": [
            "Toyota release Feb 4, 2026 announced local program updates.",
            "Argentina operations update was included in the release.",
        ],
        "key_insights": [
            "Program timing appears tied to local market strategy.",
            "Source distinguishes release date from publication date.",
        ],
        "review_status": "Pending",
        "notes": "",
    }
    rec.update(overrides)
    return rec


def test_pdf_publish_date_hint_prefers_header_over_metadata():
    text = (
        "Toyota Argentina\n"
        "Feb 07, 2026\n"
        "On February 4, 2026, Toyota released program details.\n"
    )
    date_iso, source = extract_pdf_publish_date_hint(
        b"",
        extracted_text=text,
        metadata_date_hint="2026-02-05",
    )
    assert date_iso == "2026-02-07"
    assert source == "pdf_header_publish_date"


def test_pdf_publish_date_hint_falls_back_to_metadata_if_header_missing():
    text = "Toyota Argentina operations update without a visible header date."
    date_iso, source = extract_pdf_publish_date_hint(
        b"",
        extracted_text=text,
        metadata_date_hint="D:20260207120000-03'00'",
    )
    assert date_iso == "2026-02-07"
    assert source == "pdf_metadata_publish_date"


def test_toyota_argentina_pdf_publish_date_regression():
    rec = _base_record()
    source_text = (
        "Toyota Argentina\n"
        "Feb 07, 2026\n"
        "On February 4, 2026, Toyota released updates for local operations.\n"
    )

    out = postprocess_record(
        rec,
        source_text=source_text,
        publish_date_hint="2026-02-07",
        publish_date_hint_source="pdf_header_publish_date",
    )

    assert out["publish_date"] == "2026-02-07"
    assert out.get("event_date") == "2026-02-04"
    assert any("Toyota release Feb 4, 2026" in b for b in (out.get("evidence_bullets") or []))
