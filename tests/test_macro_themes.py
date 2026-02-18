"""
Tests for macro-theme detection in postprocess.
Run with: pytest test_macro_themes.py -v
"""
import pytest
from src.postprocess import postprocess_record


def _base_record(**overrides):
    """Minimal valid record for macro-theme testing."""
    rec = {
        "title": "Test Title",
        "source_type": "Reuters",
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


# ============================================================================
# Basic firing
# ============================================================================

class TestMacroThemeFiring:

    def test_mercedes_triggers_luxury_and_margin(self):
        """Mercedes + stress keywords should fire both premium themes + rollup."""
        rec = _base_record(
            title="Mercedes profit warning amid margin pressure",
            companies_mentioned=["Mercedes-Benz"],
            keywords=["margin", "profit", "cost pressure", "premium", "auto"],
            evidence_bullets=["EBIT margin fell to 7.2%", "Sales down 8% in Q3"],
            key_insights=["Margin compression accelerating", "Cost cuts expected"],
        )
        rec = postprocess_record(rec)

        assert "Luxury OEM Stress" in rec["macro_themes_detected"]
        assert "Margin Compression at Premium OEMs" in rec["macro_themes_detected"]
        assert "Premium OEM Financial/Strategy Stress" in rec["_macro_theme_rollups"]

    def test_china_ev_fires(self):
        """BYD + EV keywords + China region should fire China EV theme."""
        rec = _base_record(
            title="BYD price war intensifies",
            companies_mentioned=["BYD"],
            keywords=["ev", "price war", "china", "competition", "auto"],
            country_mentions=["China"],
            regions_mentioned=["China"],
        )
        rec = postprocess_record(rec)

        assert "China EV Competitive Acceleration" in rec["macro_themes_detected"]
        detail = rec["_macro_theme_detail"]["China EV Competitive Acceleration"]
        assert detail["fired"] is True
        assert "companies" in detail["groups_matched"]
        assert "keywords" in detail["groups_matched"]

    def test_tariff_fires_with_us_region(self):
        """Tariff keywords + US region should fire."""
        rec = _base_record(
            title="New tariff impacts US auto imports",
            keywords=["tariff", "import duty", "customs", "auto", "trade"],
            country_mentions=["United States"],
            regions_mentioned=["US"],
        )
        rec = postprocess_record(rec)

        assert "Tariff & Trade Disruption" in rec["macro_themes_detected"]

    def test_ev_slowdown_fires(self):
        """EV delay keywords + powertrain topic should fire."""
        rec = _base_record(
            title="OEMs delay EV targets",
            topics=["OEM Strategy & Powertrain Shifts"],
            keywords=["ev delay", "hybrid pivot", "electrification", "auto", "oem"],
            evidence_bullets=["GM pushed EV target to 2030", "Ford paused EV plant"],
        )
        rec = postprocess_record(rec)

        assert "EV Transition Slowdown" in rec["macro_themes_detected"]

    def test_software_defined_fires(self):
        """SDV keywords + tech topic should fire."""
        rec = _base_record(
            title="SDV platform rollout accelerates",
            topics=["Technology Partnerships & Components"],
            keywords=["sdv", "software defined", "digital cockpit", "ota", "auto"],
        )
        rec = postprocess_record(rec)

        assert "Software-Defined Premium Shift" in rec["macro_themes_detected"]

    def test_software_defined_does_not_fire_from_notes_only(self):
        """SDV should not use analyst notes as source evidence."""
        rec = _base_record(
            title="Mercedes update",
            topics=["Market & Competition"],
            keywords=["auto"],
            evidence_bullets=["Vehicle update announced."],
            key_insights=["No software details in source fields."],
            notes="SDV infotainment AI assistant voice controls with OpenAI and Google.",
        )
        rec = postprocess_record(rec)

        assert "Software-Defined Premium Shift" not in rec["macro_themes_detected"]
        for detail in (rec.get("_macro_theme_detail") or {}).values():
            for group_match in (detail.get("matches") or {}).values():
                fields = group_match.get("fields", []) if isinstance(group_match, dict) else []
                assert all(not str(f).startswith("notes") for f in fields)


# ============================================================================
# Anti-keyword suppression
# ============================================================================

class TestAntiKeywordSuppression:

    def test_anti_keyword_suppresses_weak_signal(self):
        """Anti-keyword 'record profit' should suppress Luxury OEM Stress at 2 groups."""
        rec = _base_record(
            title="BMW posts record profit despite market fears",
            companies_mentioned=["BMW"],
            keywords=["margin", "profit", "bmw", "auto", "record"],
            evidence_bullets=["BMW record profit of EUR 10.5B", "Margin at 12%"],
        )
        rec = postprocess_record(rec)

        detail = rec["_macro_theme_detail"].get("Luxury OEM Stress", {})
        assert detail.get("fired") is False
        assert detail.get("suppressed_by_anti_keyword") is True

    def test_anti_keyword_does_not_suppress_strong_signal(self):
        """Anti-keyword should NOT suppress when >=3 groups match."""
        rec = _base_record(
            title="BMW record profit but margin concerns in luxury segment",
            companies_mentioned=["BMW"],
            topics=["Financial & Business Performance"],
            keywords=["margin", "cost cut", "restructur", "record profit", "auto"],
            evidence_bullets=["Record profit noted", "But margin declined from prior year"],
            regions_mentioned=["Europe (including Russia)"],
            country_mentions=["Germany"],
        )
        rec = postprocess_record(rec)

        # The record has companies (BMW) + keywords (margin, cost cut) = 2 groups
        # anti_keyword "record\s*profit" matches, 2 < 3, so it SHOULD suppress
        detail = rec["_macro_theme_detail"].get("Luxury OEM Stress", {})
        # With only 2 groups and anti-keyword hit, should be suppressed
        assert detail.get("fired") is False


# ============================================================================
# Region gating
# ============================================================================

class TestRegionGating:

    def test_tariff_suppressed_without_required_region(self):
        """Tariff theme needs US/China/Europe — Thailand alone should not satisfy region_requirements."""
        rec = _base_record(
            title="Tariff on Thai imports",
            keywords=["tariff", "trade barrier", "nearshoring", "thai", "auto"],
            country_mentions=["Thailand"],
            regions_mentioned=["Thailand"],
        )
        rec = postprocess_record(rec)

        detail = rec["_macro_theme_detail"].get("Tariff & Trade Disruption", {})
        assert detail.get("fired") is False
        assert detail.get("suppressed_by_region_requirement") is True

    def test_tariff_fires_with_china_region(self):
        """Tariff + China region should fire."""
        rec = _base_record(
            title="US-China tariff escalation",
            keywords=["tariff", "trade war", "customs", "china", "auto"],
            country_mentions=["China"],
            regions_mentioned=["China"],
        )
        rec = postprocess_record(rec)

        assert "Tariff & Trade Disruption" in rec["macro_themes_detected"]


class TestRegionBucketingOptionB:

    def test_germany_maps_to_western_europe(self):
        rec = _base_record(country_mentions=["Germany"])
        out = postprocess_record(rec)
        assert "Western Europe" in out.get("regions_relevant_to_kiekert", [])

    def test_poland_maps_to_eastern_europe(self):
        rec = _base_record(country_mentions=["Poland"])
        out = postprocess_record(rec)
        assert "Eastern Europe" in out.get("regions_relevant_to_kiekert", [])

    def test_russia_maps_to_russia_bucket(self):
        rec = _base_record(country_mentions=["Russia"])
        out = postprocess_record(rec)
        assert "Russia" in out.get("regions_relevant_to_kiekert", [])

    def test_generic_europe_defaults_to_western_with_ambiguity_flag(self):
        rec = _base_record(
            title="Europe suppliers face margin pressure",
            country_mentions=[],
            regions_mentioned=[],
            regions_relevant_to_kiekert=[],
        )
        out = postprocess_record(rec)
        assert "Western Europe" in out.get("regions_mentioned", [])
        assert "Europe_generic_defaulted_to_Western_Europe" in (out.get("_region_ambiguity") or [])

    def test_legacy_europe_including_russia_migrates_to_western_only(self):
        rec = _base_record(
            country_mentions=[],
            regions_mentioned=["Europe (including Russia)"],
            regions_relevant_to_kiekert=["Europe (including Russia)"],
        )
        out = postprocess_record(rec)
        assert "Western Europe" in out.get("regions_mentioned", [])
        assert "Russia" not in out.get("regions_mentioned", [])
        assert "Western Europe" in out.get("regions_relevant_to_kiekert", [])
        assert "Russia" not in out.get("regions_relevant_to_kiekert", [])
        migrations = out.get("_region_migrations") or []
        assert {"from": "Europe (including Russia)", "to": "Western Europe"} in migrations

    def test_toyota_argentina_maps_to_latin_america_and_never_us_without_us_signal(self):
        rec = _base_record(
            title="Toyota Argentina production update",
            country_mentions=["Argentina"],
            regions_mentioned=["US"],  # Simulate bad extraction.
            regions_relevant_to_kiekert=[],
            evidence_bullets=[
                "Toyota release Feb 4, 2026 announced local program updates.",
                "Argentina operations update was included in the release.",
            ],
        )
        source_text = (
            "Toyota Argentina\n"
            "Feb 07, 2026\n"
            "On February 4, 2026, Toyota released updates for local operations in Argentina.\n"
        )
        out = postprocess_record(rec, source_text=source_text)

        assert "Latin America" in out.get("regions_mentioned", [])
        assert "US" not in out.get("regions_mentioned", [])
        assert "Latin America" in out.get("regions_relevant_to_kiekert", [])


# ============================================================================
# Premium company gate
# ============================================================================

class TestPremiumCompanyGate:

    def test_non_premium_company_blocked(self):
        """Toyota is not in PREMIUM_OEMS — should not fire Luxury OEM Stress."""
        rec = _base_record(
            title="Toyota profit warning as sales decline",
            companies_mentioned=["Toyota"],
            keywords=["margin", "profit warn", "sales decline", "auto", "oem"],
        )
        rec = postprocess_record(rec)

        detail = rec["_macro_theme_detail"].get("Luxury OEM Stress", {})
        assert detail.get("fired") is False
        assert detail.get("suppressed_by_premium_gate") is True


# ============================================================================
# Strength scoring
# ============================================================================

class TestStrength:

    def test_strength_2_groups(self):
        """2 groups matched -> strength 1."""
        rec = _base_record(
            title="BYD EV exports surge",
            companies_mentioned=["BYD"],
            keywords=["ev export", "market share", "auto", "byd", "china"],
            country_mentions=["China"],
            regions_mentioned=["China"],
        )
        rec = postprocess_record(rec)

        strength = rec["_macro_theme_strength"].get("China EV Competitive Acceleration", 0)
        assert strength >= 1

    def test_strength_3_groups(self):
        """3 groups matched -> strength 2."""
        rec = _base_record(
            title="BYD EV exports surge from China",
            companies_mentioned=["BYD"],
            keywords=["ev export", "market share", "competition", "auto", "byd"],
            country_mentions=["China"],
            regions_mentioned=["China"],
        )
        rec = postprocess_record(rec)

        strength = rec["_macro_theme_strength"].get("China EV Competitive Acceleration", 0)
        # companies + keywords + regions = 3 groups -> strength 2
        assert strength == 2


# ============================================================================
# Rollup clusters
# ============================================================================

class TestRollups:

    def test_rollup_produced_for_overlapping_themes(self):
        """When both Luxury OEM Stress and Margin Compression fire, rollup should appear."""
        rec = _base_record(
            title="Porsche margin under cost pressure amid downturn",
            companies_mentioned=["Porsche"],
            keywords=["margin", "cost pressure", "profit", "downturn", "auto"],
            evidence_bullets=["EBIT margin fell", "Cost cuts announced"],
            key_insights=["Margin compression", "Restructuring expected"],
        )
        rec = postprocess_record(rec)

        assert "Premium OEM Financial/Strategy Stress" in rec["_macro_theme_rollups"]

    def test_no_rollup_when_no_overlap(self):
        """Themes without rollup field should not pollute rollups."""
        rec = _base_record(
            title="SDV digital cockpit OTA update",
            topics=["Technology Partnerships & Components"],
            keywords=["sdv", "digital cockpit", "ota", "connected car", "auto"],
        )
        rec = postprocess_record(rec)

        assert rec["_macro_theme_rollups"] == []

    def test_china_and_sdv_structural_rollup_fires(self):
        rec = _base_record(
            title="BYD and Nvidia expand AI cockpit strategy in China",
            topics=["Technology Partnerships & Components"],
            companies_mentioned=["BYD", "Nvidia Corp."],
            keywords=["price war", "china", "voice controls", "infotainment", "software defined"],
            country_mentions=["China"],
            regions_mentioned=["China"],
        )
        rec = postprocess_record(rec)

        assert "China EV Competitive Acceleration" in rec["macro_themes_detected"]
        assert "Software-Defined Premium Shift" in rec["macro_themes_detected"]
        assert "China Tech-Driven Premium Disruption" in rec["_macro_theme_rollups"]


# ============================================================================
# Rich audit detail
# ============================================================================

class TestAuditDetail:

    def test_detail_includes_field_locations(self):
        """Keyword matches should report which fields they hit."""
        rec = _base_record(
            title="BYD price war heats up in China",
            companies_mentioned=["BYD"],
            keywords=["ev", "price war", "byd", "china", "competition"],
            country_mentions=["China"],
            regions_mentioned=["China"],
            evidence_bullets=["EV exports up 40%", "Price war intensifies"],
        )
        rec = postprocess_record(rec)

        detail = rec["_macro_theme_detail"]["China EV Competitive Acceleration"]
        assert detail["fired"] is True
        kw_match = detail["matches"].get("keywords", {})
        assert len(kw_match.get("fields", [])) > 0

    def test_detail_keyed_by_theme_name(self):
        """_macro_theme_detail should be a dict keyed by theme name."""
        rec = _base_record()
        rec = postprocess_record(rec)

        assert isinstance(rec["_macro_theme_detail"], dict)
        for key in rec["_macro_theme_detail"]:
            assert isinstance(key, str)


# ============================================================================
# Backward compatibility
# ============================================================================

class TestBackwardCompat:

    def test_macro_themes_detected_is_list_of_strings(self):
        """macro_themes_detected must remain a plain list of strings."""
        rec = _base_record()
        rec = postprocess_record(rec)

        assert isinstance(rec["macro_themes_detected"], list)
        for item in rec["macro_themes_detected"]:
            assert isinstance(item, str)

    def test_no_themes_produces_empty_list(self):
        """Record with no matching signals should produce empty list."""
        rec = _base_record(
            title="Routine corporate filing",
            companies_mentioned=["Acme Corp"],
            keywords=["filing", "routine", "corporate", "quarterly", "report"],
        )
        rec = postprocess_record(rec)

        assert rec["macro_themes_detected"] == []
        assert rec["_macro_theme_rollups"] == []


# ============================================================================
# Macro theme priority escalation
# ============================================================================

class TestMacroThemePriorityEscalation:

    def test_tariff_theme_with_footprint_escalates_priority_high(self):
        rec = _base_record(
            title="US tariff disruption raises sourcing risk",
            priority="Medium",
            keywords=["tariff", "trade war", "import duty", "customs", "auto"],
            country_mentions=["United States"],
            regions_mentioned=[],
            regions_relevant_to_kiekert=[],
        )
        out = postprocess_record(rec)

        assert "Tariff & Trade Disruption" in out["macro_themes_detected"]
        assert out.get("priority") == "High"
        assert out.get("priority_final") == "High"
        assert out.get("priority_reason") == "footprint_and_macro_theme:Tariff & Trade Disruption"

    def test_theme_without_footprint_does_not_escalate(self):
        rec = _base_record(
            title="Mercedes warns on margin pressure",
            priority="Medium",
            companies_mentioned=["Mercedes-Benz"],
            keywords=["margin", "profit warn", "cost pressure", "premium", "auto"],
            country_mentions=[],
            regions_mentioned=[],
            regions_relevant_to_kiekert=[],
        )
        out = postprocess_record(rec)

        assert "Luxury OEM Stress" in out["macro_themes_detected"]
        assert out.get("regions_relevant_to_kiekert") == []
        assert out.get("priority") == "Medium"
        assert out.get("priority_final") == "Medium"
        assert out.get("priority_reason") != "footprint_and_macro_theme:Luxury OEM Stress"

    def test_existing_priority_rule_reason_preserved_when_already_high(self):
        rec = _base_record(
            title="Mercedes margin pressure in Germany",
            priority="Medium",
            companies_mentioned=["Mercedes-Benz"],
            keywords=["margin", "cost pressure", "profit", "auto", "premium"],
            country_mentions=["Germany"],
            regions_mentioned=[],
            regions_relevant_to_kiekert=[],
        )
        out = postprocess_record(rec)

        assert "Luxury OEM Stress" in out["macro_themes_detected"]
        assert out.get("priority") == "High"
        assert out.get("priority_reason") == "footprint_and_key_oem"

    def test_toyota_motor_corporation_hits_key_oem_priority_path(self):
        rec = _base_record(
            title="Toyota Motor Corporation updates sourcing in Japan",
            priority="Medium",
            companies_mentioned=["Toyota Motor Corporation"],
            keywords=["sourcing", "platform", "production", "automotive", "oem"],
            country_mentions=["Japan"],
            regions_mentioned=[],
            regions_relevant_to_kiekert=[],
        )
        out = postprocess_record(rec)

        assert "Japan" in out.get("regions_relevant_to_kiekert", [])
        assert "Toyota" in out.get("companies_mentioned", [])
        assert out.get("priority") == "High"
        assert out.get("priority_reason") == "footprint_and_key_oem"


# ============================================================================
# Regression: Mercedes Bloomberg issues
# ============================================================================

class TestMercedesBloombergRegression:

    def test_mentions_our_company_deterministic_false_and_no_priority_reason_mentions(self):
        rec = _base_record(
            title="Mercedes debuts CLA with AI voice assistant",
            source_type="Bloomberg",
            publish_date="2026-01-29",
            publish_date_confidence="High",
            mentions_our_company=True,  # Simulate bad LLM output
            companies_mentioned=["Mercedes-Benz"],
            country_mentions=["United States"],
            keywords=["launch", "mercedes", "cla", "voice controls", "ai"],
        )
        out = postprocess_record(rec)

        assert out["mentions_our_company"] is False
        assert out.get("priority_reason") != "mentions_our_company"

    def test_mentions_alias_in_notes_only_does_not_count_as_source_mention(self):
        rec = _base_record(
            title="Mercedes debuts CLA with AI voice assistant",
            source_type="Bloomberg",
            mentions_our_company=True,  # Simulate bad LLM output
            notes="It does not mention Kiekert.",
            keywords=["mercedes", "cla", "voice controls"],
            evidence_bullets=["Mercedes introduced new voice controls for CLA."],
            key_insights=["AI assistant partnership was highlighted."],
        )
        out = postprocess_record(rec)

        assert out["mentions_our_company"] is False
        assert out.get("_provenance", {}).get("mentions_our_company", {}).get("reason") == "company_alias_not_found"
        assert out.get("priority_reason") != "mentions_our_company"

    def test_bloomberg_header_timestamp_overrides_event_date(self):
        rec = _base_record(
            title="Mercedes unveils CLA EV",
            source_type="Bloomberg",
            publish_date="2026-01-29",  # Event date incorrectly extracted by LLM
            publish_date_confidence="High",
            keywords=["mercedes", "ev", "launch", "software", "voice controls"],
        )
        source_text = (
            "Bloomberg\n"
            "February 1, 2026 at 9:00 PM PST\n"
            "Mercedes-Benz unveiled its CLA EV on Jan. 29 in Berlin.\n"
        )
        out = postprocess_record(rec, source_text=source_text)

        assert out["publish_date"] == "2026-02-01"
        assert out["publish_date_confidence"] == "High"
        assert out.get("_provenance", {}).get("publish_date", {}).get("source") == "rule:bloomberg_header_publish_date"
        assert out.get("_publisher_date_override_applied") is True
        assert out.get("_publisher_date_override_source") == "rule:bloomberg_header_publish_date"

    def test_bloomberg_header_not_used_as_event_date(self):
        rec = _base_record(
            title="Mercedes unveils CLA EV",
            source_type="Bloomberg",
            publish_date="2026-02-01",
            publish_date_confidence="High",
            keywords=["mercedes", "ev", "launch", "software", "voice controls"],
        )
        source_text = (
            "Bloomberg\n"
            "February 1, 2026 at 9:00 PM PST\n"
            "The launch event took place on January 29, 2026 in Berlin.\n"
        )
        out = postprocess_record(rec, source_text=source_text)

        assert out["publish_date"] == "2026-02-01"
        assert out.get("event_date") in (None, "2026-01-29")
        assert out.get("event_date") != out["publish_date"]

    def test_no_override_when_publisher_parser_returns_none(self):
        rec = _base_record(
            title="Mercedes unveils CLA EV",
            source_type="Bloomberg",
            publish_date="2026-01-29",
            publish_date_confidence="Medium",
            keywords=["mercedes", "ev", "launch", "software", "voice controls"],
        )
        source_text = (
            "Bloomberg\n"
            "Mercedes-Benz unveiled its CLA EV on Jan. 29 in Berlin.\n"
            "No header timestamp line is present in this snippet.\n"
        )
        out = postprocess_record(rec, source_text=source_text)

        assert out["publish_date"] == "2026-01-29"
        assert out["publish_date_confidence"] == "Medium"
        assert out.get("_publisher_date_override_applied") is False
        assert out.get("_publisher_date_override_source") is None

    def test_header_date_match_existing_publish_date_does_not_set_override_flags(self):
        rec = _base_record(
            title="Mercedes unveils CLA EV",
            source_type="Bloomberg",
            publish_date="2026-02-01",
            publish_date_confidence="Medium",
            keywords=["mercedes", "ev", "launch", "software", "voice controls"],
        )
        source_text = (
            "Bloomberg\n"
            "February 1, 2026 at 9:00 PM PST\n"
            "Mercedes-Benz showcased software features.\n"
        )
        out = postprocess_record(rec, source_text=source_text)

        assert out["publish_date"] == "2026-02-01"
        assert out["publish_date_confidence"] == "Medium"
        assert out.get("_publisher_date_override_applied") is False
        assert out.get("_publisher_date_override_source") is None

    def test_sdv_theme_fires_from_ai_voice_controls_signals(self):
        rec = _base_record(
            title="Mercedes software cockpit update",
            source_type="Bloomberg",
            topics=["Technology Partnerships & Components"],
            companies_mentioned=["Nvidia Corp.", "Huawei Technologies Co."],
            keywords=["mercedes", "cla", "update", "premium", "voice controls"],
            evidence_bullets=[
                "OpenAI and Microsoft-powered AI voice controls are integrated.",
                "Google infotainment features are included in the new vehicle software stack.",
            ],
            notes="Analyst: mentions SDV in commentary only.",
        )
        out = postprocess_record(rec)

        assert "Software-Defined Premium Shift" in out["macro_themes_detected"]
        sdv_detail = out["_macro_theme_detail"]["Software-Defined Premium Shift"]
        assert "companies" in sdv_detail.get("groups_matched", [])
        assert "keywords" in sdv_detail.get("groups_matched", [])
        assert "topics" in sdv_detail.get("groups_matched", [])
        assert out.get("_macro_theme_strength", {}).get("Software-Defined Premium Shift") == 2
        kw_fields = sdv_detail.get("matches", {}).get("keywords", {}).get("fields", [])
        assert all(not str(f).startswith("notes") for f in kw_fields)
        for group_match in (sdv_detail.get("matches") or {}).values():
            fields = group_match.get("fields", []) if isinstance(group_match, dict) else []
            assert all(not str(f).startswith("notes") for f in fields)

    def test_legal_entity_company_normalization_restores_premium_and_priority_rules(self):
        rec = _base_record(
            title="Mercedes margin under pressure",
            source_type="Bloomberg",
            priority="Medium",
            companies_mentioned=["Mercedes-Benz Group AG"],
            keywords=["margin", "cost pressure", "profit", "voice controls"],
            country_mentions=["Germany"],
            evidence_bullets=["EBIT margin fell amid software transition costs."],
            key_insights=["Supplier squeeze likely to continue this quarter."],
        )
        out = postprocess_record(rec)

        assert "Mercedes-Benz" in out.get("companies_mentioned", [])
        lux_detail = out["_macro_theme_detail"]["Luxury OEM Stress"]
        margin_detail = out["_macro_theme_detail"]["Margin Compression at Premium OEMs"]
        assert lux_detail.get("fired") is True
        assert not lux_detail.get("suppressed_by_premium_gate", False)
        assert margin_detail.get("fired") is True
        assert not margin_detail.get("suppressed_by_premium_gate", False)
        assert out.get("priority_final") == "High"
        assert out.get("priority_reason") == "footprint_and_key_oem"

    def test_confidence_computation_does_not_double_count_on_reprocess(self):
        rec = _base_record(
            title="Mercedes software cockpit update",
            source_type="Bloomberg",
            confidence="Medium",
            publish_date="2026-02-01",
            publish_date_confidence="High",
            companies_mentioned=["Mercedes-Benz Group AG"],
            country_mentions=["Germany"],
            evidence_bullets=[
                "OpenAI and Microsoft-powered AI voice controls are integrated.",
                "Google infotainment features are included in the new vehicle software stack.",
                "Supplier integration cost is expected this quarter.",
            ],
            key_insights=["One", "Two"],
        )
        out1 = postprocess_record(rec)
        out2 = postprocess_record(out1)

        assert int((out2.get("_rule_impact") or {}).get("computed_confidence", 0)) <= 1
        conf_mutations = [m for m in (out2.get("_mutations") or []) if m.get("field") == "confidence"]
        assert len(conf_mutations) <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
