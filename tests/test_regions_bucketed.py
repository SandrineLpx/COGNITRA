"""
Regression tests for regions_bucketed_deduped logic.

regions_mentioned contains display-level region buckets only (no individual countries).
regions_relevant_to_kiekert retains country-level footprint granularity.
Country detail lives in country_mentions.

Run with: pytest tests/test_regions_bucketed.py -v
"""
import pytest
from src.postprocess import postprocess_record


def _base_record(**overrides):
    """Minimal valid record for region testing."""
    rec = {
        "title": "Test Title",
        "source_type": "Bloomberg",
        "publish_date": "2026-01-15",
        "publish_date_confidence": "High",
        "original_url": None,
        "actor_type": "oem",
        "government_entities": [],
        "companies_mentioned": [],
        "mentions_our_company": False,
        "topics": ["Market & Competition"],
        "keywords": ["auto"],
        "country_mentions": [],
        "regions_mentioned": [],
        "regions_relevant_to_kiekert": [],
        "evidence_bullets": ["Fact one", "Fact two"],
        "key_insights": ["Insight one", "Insight two"],
        "review_status": "Pending",
        "notes": "",
    }
    rec.update(overrides)
    return rec


class TestRegionsBucketedDeduped:
    """regions_mentioned must contain only display-level region buckets."""

    def test_bloomberg_toyota_ceo_regions_are_display_level(self):
        """Bloomberg Toyota CEO article: regions_mentioned should have
        display buckets (Asia, US) — not countries (Japan, China).
        Country detail preserved in regions_relevant_to_kiekert.
        """
        rec = _base_record(
            title="Toyota CEO Discusses Tariff Impact in Tokyo Press Conference",
            regions_mentioned=["Asia"],
            country_mentions=["Japan", "United States", "China"],
            keywords=["tariff", "Toyota", "CEO", "Tokyo"],
            evidence_bullets=[
                "Toyota CEO spoke at Tokyo headquarters about US tariff risks",
                "China market share declining amid competition",
            ],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        # Display regions only
        assert "Asia" in regions, f"Asia missing; got {regions}"
        assert "US" in regions, f"US missing; got {regions}"
        # No country-level entries in regions_mentioned
        assert "Japan" not in regions, f"Japan should not be in regions_mentioned; got {regions}"
        assert "China" not in regions, f"China should not be in regions_mentioned; got {regions}"
        # Country-level detail preserved in kiekert field
        assert "Japan" in kiekert, f"Japan missing from regions_relevant_to_kiekert; got {kiekert}"
        assert "China" in kiekert, f"China missing from regions_relevant_to_kiekert; got {kiekert}"

    def test_japan_country_maps_to_asia_display(self):
        """Japan in country_mentions produces 'Asia' in regions_mentioned
        and 'Japan' in regions_relevant_to_kiekert."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Japan"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Asia" in regions, f"Japan did not map to Asia display; got {regions}"
        assert "Japan" not in regions, f"Japan should not be in regions_mentioned; got {regions}"
        assert "Japan" in kiekert, f"Japan missing from regions_relevant_to_kiekert; got {kiekert}"

    def test_china_country_maps_to_asia_display(self):
        """China in country_mentions produces 'Asia' in regions_mentioned
        and 'China' in regions_relevant_to_kiekert."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["China"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Asia" in regions, f"China did not map to Asia display; got {regions}"
        assert "China" not in regions, f"China should not be in regions_mentioned; got {regions}"
        assert "China" in kiekert, f"China missing from regions_relevant_to_kiekert; got {kiekert}"

    def test_india_country_maps_to_asia_display(self):
        """India in country_mentions produces 'Asia' display region."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["India"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Asia" in regions, f"India did not map to Asia display; got {regions}"
        assert "India" not in regions, f"India should not be in regions_mentioned; got {regions}"
        assert "India" in kiekert

    def test_mexico_country_maps_to_latin_america_display(self):
        """Mexico in country_mentions produces 'Latin America' display region."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Mexico"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Latin America" in regions, f"Mexico did not map to Latin America; got {regions}"
        assert "Mexico" not in regions, f"Mexico should not be in regions_mentioned; got {regions}"
        assert "Mexico" in kiekert

    def test_russia_country_maps_to_eastern_europe_display(self):
        """Russia in country_mentions produces 'Eastern Europe' display region."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Russia"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Eastern Europe" in regions, f"Russia did not map to Eastern Europe; got {regions}"
        assert "Russia" not in regions, f"Russia should not be in regions_mentioned; got {regions}"
        assert "Russia" in kiekert

    def test_tokyo_text_hint_adds_asia(self):
        """Tokyo in text should hint Asia display region."""
        rec = _base_record(
            title="Toyota announces expansion from Tokyo headquarters",
            regions_mentioned=[],
            country_mentions=["Japan"],
            keywords=["Tokyo", "expansion"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Asia" in regions, f"Tokyo hint did not produce Asia; got {regions}"

    def test_south_korea_implies_asia(self):
        """South Korea in country_mentions should derive Asia display region."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["South Korea"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Asia" in regions, f"South Korea did not derive Asia; got {regions}"

    def test_western_europe_unchanged(self):
        """Western Europe is already a display region — should pass through."""
        rec = _base_record(
            regions_mentioned=["Western Europe"],
            country_mentions=["Germany", "France"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Western Europe" in regions, f"Western Europe dropped; got {regions}"

    def test_us_display_region_preserved(self):
        """US is a display-level region — should survive."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["United States"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "US" in regions, f"US dropped; got {regions}"

    def test_multiple_asian_countries_collapse_to_single_asia(self):
        """Multiple Asian countries should all collapse to one 'Asia' entry."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Japan", "China", "India", "Thailand"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert regions.count("Asia") == 1, f"Expected single Asia; got {regions}"
        assert len(regions) == 1, f"Expected only ['Asia']; got {regions}"
        # But kiekert retains granularity
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Japan" in kiekert
        assert "China" in kiekert
        assert "India" in kiekert
        assert "Thailand" in kiekert

    def test_primary_display_region_preserved_order(self):
        """Primary region should appear before secondary derived regions."""
        rec = _base_record(
            regions_mentioned=["Asia"],
            country_mentions=["Japan", "United States"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        asia_idx = regions.index("Asia")
        us_idx = regions.index("US")
        assert asia_idx < us_idx, f"Asia should come before US; got {regions}"

    def test_canada_maps_to_us_region(self):
        """Canada should map to US display region (USMCA trade partner)."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Canada"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "US" in regions, f"Canada did not map to US; got {regions}"

    def test_sweden_maps_to_western_europe(self):
        """Sweden (Volvo) should map to Western Europe."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Sweden"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Western Europe" in regions, f"Sweden did not map to Western Europe; got {regions}"

    def test_vietnam_maps_to_asia(self):
        """Vietnam should map to Asia display region."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Vietnam"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Asia" in regions, f"Vietnam did not map to Asia; got {regions}"

    def test_no_country_names_in_regions_mentioned(self):
        """regions_mentioned must never contain individual country names."""
        from src.constants import FOOTPRINT_TO_DISPLAY
        rec = _base_record(
            regions_mentioned=["India", "China", "Japan", "Thailand", "Mexico", "Russia"],
            country_mentions=["India", "China", "Japan", "Thailand", "Mexico", "Russia"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        for country in FOOTPRINT_TO_DISPLAY:
            assert country not in regions, f"{country} leaked into regions_mentioned; got {regions}"


class TestSchemaRelaxation:
    """Verify relaxed cardinality constraints accept wider ranges."""

    def test_four_topics_valid(self):
        """Records with 4 topics should pass validation."""
        from src.schema_validate import validate_record
        rec = _base_record(
            topics=[
                "Market & Competition",
                "Financial & Business Performance",
                "OEM Strategy & Powertrain Shifts",
                "Supply Chain & Manufacturing",
            ],
            keywords=["auto", "ev", "market", "share", "oem"],
        )
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"4-topic record rejected: {errs}"

    def test_three_keywords_valid(self):
        """Records with only 3 keywords should pass validation."""
        from src.schema_validate import validate_record
        rec = _base_record(keywords=["auto", "ev", "market"])
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"3-keyword record rejected: {errs}"

    def test_fifteen_keywords_valid(self):
        """Records with 15 keywords should pass validation."""
        from src.schema_validate import validate_record
        kw = [f"keyword_{i}" for i in range(15)]
        rec = _base_record(keywords=kw)
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"15-keyword record rejected: {errs}"

    def test_technology_actor_type_valid(self):
        """actor_type='technology' should pass validation."""
        from src.schema_validate import validate_record
        rec = _base_record(
            actor_type="technology",
            keywords=["nvidia", "gpu", "autonomous", "driving", "ai"],
        )
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"technology actor_type rejected: {errs}"

    def test_financial_news_source_type_valid(self):
        """source_type='Financial News' should pass validation."""
        from src.schema_validate import validate_record
        rec = _base_record(
            source_type="Financial News",
            keywords=["wsj", "automotive", "earnings", "market", "profit"],
        )
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"Financial News source_type rejected: {errs}"

    def test_industry_publication_source_type_valid(self):
        """source_type='Industry Publication' should pass validation."""
        from src.schema_validate import validate_record
        rec = _base_record(
            source_type="Industry Publication",
            keywords=["logistics", "supply", "chain", "automotive", "tier1"],
        )
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"Industry Publication source_type rejected: {errs}"

    def test_marklines_alias_normalized(self):
        """source_type='Marklines' should normalize to canonical 'MarkLines'."""
        from src.schema_validate import validate_record
        rec = _base_record(
            source_type="Marklines",
            keywords=["supplier", "automotive", "market", "forecast", "oem"],
        )
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        assert ok, f"Marklines alias normalization failed validation: {errs}"
        assert rec.get("source_type") == "MarkLines"
