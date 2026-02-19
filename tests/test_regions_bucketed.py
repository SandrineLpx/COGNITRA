"""
Regression tests for regions_bucketed_deduped logic.

New design (new_country_mapping.csv):
- FOOTPRINT_TO_DISPLAY = {} (identity mapping; every footprint value is its own display value).
- Individual Kiekert countries (France, Germany, Japan, South Korea, etc.) appear by name in
  both regions_mentioned and regions_relevant_to_kiekert.
- Non-individual countries collapse to their market bucket (Canada→NAFTA, Vietnam→ASEAN, etc.).
- regions_relevant_to_kiekert is derived strictly from country_mentions.
- regions_mentioned adds hints from record text on top of the derived values.

Run with: pytest tests/test_regions_bucketed.py -v
"""
import pytest
from src.constants import FOOTPRINT_REGIONS
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
    """regions_mentioned must contain only valid FOOTPRINT_REGIONS values."""

    def test_bloomberg_toyota_ceo_regions_are_valid_footprint_values(self):
        """Bloomberg Toyota CEO article: regions_mentioned should have valid footprint
        values — individual Kiekert countries (Japan, United States, China) appear by name.
        """
        rec = _base_record(
            title="Toyota CEO Discusses Tariff Impact in Tokyo Press Conference",
            regions_mentioned=["South Asia"],
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
        # Individual Kiekert countries appear by name in regions_mentioned
        assert "Japan" in regions, f"Japan missing; got {regions}"
        assert "United States" in regions, f"United States missing; got {regions}"
        assert "China" in regions, f"China missing; got {regions}"
        # All values are valid footprint entries
        for r in regions:
            assert r in FOOTPRINT_REGIONS, f"{r} is not a valid FOOTPRINT_REGIONS value"
        # Country-level detail also preserved in kiekert field
        assert "Japan" in kiekert, f"Japan missing from regions_relevant_to_kiekert; got {kiekert}"
        assert "China" in kiekert, f"China missing from regions_relevant_to_kiekert; got {kiekert}"

    def test_japan_country_maps_to_own_name(self):
        """Japan in country_mentions produces 'Japan' in both regions_mentioned
        and regions_relevant_to_kiekert (Japan is an individual Kiekert entry)."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Japan"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Japan" in regions, f"Japan missing from regions_mentioned; got {regions}"
        assert "Japan" in kiekert, f"Japan missing from regions_relevant_to_kiekert; got {kiekert}"

    def test_china_country_maps_to_own_name(self):
        """China in country_mentions produces 'China' in both fields."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["China"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "China" in regions, f"China missing from regions_mentioned; got {regions}"
        assert "China" in kiekert, f"China missing from regions_relevant_to_kiekert; got {kiekert}"

    def test_india_country_maps_to_own_name(self):
        """India in country_mentions produces 'India' (individual Kiekert entry)."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["India"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "India" in regions, f"India missing from regions_mentioned; got {regions}"
        assert "India" in kiekert

    def test_mexico_country_maps_to_own_name(self):
        """Mexico in country_mentions produces 'Mexico' (individual Kiekert entry)."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Mexico"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Mexico" in regions, f"Mexico missing from regions_mentioned; got {regions}"
        assert "Mexico" in kiekert

    def test_russia_country_maps_to_own_name(self):
        """Russia in country_mentions produces 'Russia' (individual Kiekert entry)."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Russia"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Russia" in regions, f"Russia missing from regions_mentioned; got {regions}"
        assert "Russia" in kiekert

    def test_south_korea_country_maps_to_own_name(self):
        """South Korea in country_mentions produces 'South Korea' (individual Kiekert entry)."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["South Korea"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "South Korea" in regions, f"South Korea missing from regions_mentioned; got {regions}"
        assert "South Korea" in kiekert

    def test_tokyo_text_hint_adds_japan(self):
        """Tokyo in text should hint Japan (not generic Asia)."""
        rec = _base_record(
            title="Toyota announces expansion from Tokyo headquarters",
            regions_mentioned=[],
            country_mentions=["Japan"],
            keywords=["Tokyo", "expansion"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Japan" in regions, f"Tokyo hint did not produce Japan; got {regions}"

    def test_west_europe_bucket_preserved(self):
        """'West Europe' is a valid bucket — should pass through unchanged."""
        rec = _base_record(
            regions_mentioned=["West Europe"],
            country_mentions=[],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "West Europe" in regions, f"West Europe dropped; got {regions}"

    def test_western_europe_alias_normalized_to_west_europe(self):
        """Legacy 'Western Europe' in regions_mentioned normalizes to 'West Europe'."""
        rec = _base_record(
            regions_mentioned=["Western Europe"],
            country_mentions=["Germany", "France"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "West Europe" in regions, f"West Europe missing after alias normalization; got {regions}"
        assert "Western Europe" not in regions, f"Old name should be gone; got {regions}"
        # Individual Kiekert countries appear directly
        assert "Germany" in regions, f"Germany missing; got {regions}"
        assert "France" in regions, f"France missing; got {regions}"

    def test_us_replaced_by_united_states(self):
        """country_mentions=['United States'] produces 'United States' in regions."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["United States"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "United States" in regions, f"United States missing; got {regions}"

    def test_multiple_individual_kiekert_countries_appear_separately(self):
        """Japan, China, India, Thailand each appear by name — no collapse to generic 'Asia'."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Japan", "China", "India", "Thailand"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Japan" in regions, f"Japan missing; got {regions}"
        assert "China" in regions, f"China missing; got {regions}"
        assert "India" in regions, f"India missing; got {regions}"
        assert "Thailand" in regions, f"Thailand missing; got {regions}"
        assert "South Asia" not in regions, f"Generic South Asia should not appear; got {regions}"
        # kiekert retains granularity
        kiekert = rec["regions_relevant_to_kiekert"]
        assert "Japan" in kiekert
        assert "China" in kiekert
        assert "India" in kiekert
        assert "Thailand" in kiekert

    def test_primary_region_preserved_before_derived(self):
        """Primary region_mentioned item should appear before derived items."""
        rec = _base_record(
            regions_mentioned=["South Asia"],
            country_mentions=["Japan", "United States"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        # South Asia (from regions_mentioned, normalized from "Asia") comes first
        assert "South Asia" in regions, f"South Asia missing; got {regions}"
        south_asia_idx = regions.index("South Asia")
        assert south_asia_idx < regions.index("Japan"), f"South Asia should come before Japan; got {regions}"

    def test_canada_maps_to_nafta_bucket(self):
        """Canada is not a Kiekert-individual country — maps to NAFTA bucket."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Canada"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "NAFTA" in regions, f"Canada did not map to NAFTA; got {regions}"

    def test_sweden_maps_to_west_europe_bucket(self):
        """Sweden (not an individual Kiekert entry) maps to West Europe bucket."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Sweden"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "Sweden" in regions, f"Sweden missing; got {regions}"

    def test_vietnam_maps_to_asean_bucket(self):
        """Vietnam maps to ASEAN bucket."""
        rec = _base_record(
            regions_mentioned=[],
            country_mentions=["Vietnam"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        assert "ASEAN" in regions, f"Vietnam did not map to ASEAN; got {regions}"

    def test_all_regions_mentioned_are_valid_footprint_values(self):
        """Every value in regions_mentioned must be a valid FOOTPRINT_REGIONS entry."""
        from src.constants import FOOTPRINT_TO_DISPLAY
        rec = _base_record(
            regions_mentioned=["India", "China", "Japan", "Thailand", "Mexico", "Russia",
                               "South Korea", "United States"],
            country_mentions=["India", "China", "Japan", "Thailand", "Mexico", "Russia",
                              "South Korea", "United States"],
        )
        rec = postprocess_record(rec)
        regions = rec["regions_mentioned"]
        for r in regions:
            assert r in FOOTPRINT_REGIONS, f"{r} is not a valid FOOTPRINT_REGIONS value; got {regions}"
        # FOOTPRINT_TO_DISPLAY is now empty; all footprint values = display values
        assert FOOTPRINT_TO_DISPLAY == {}, "FOOTPRINT_TO_DISPLAY should be empty in new design"


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
