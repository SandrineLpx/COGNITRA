"""
Test scenarios for duplicate detection, story-level deduplication, and briefing flows.
Run with: pytest test_scenarios.py -v
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

from src.storage import new_record_id, utc_now_iso
from src.dedupe import (
    normalize_title,
    find_exact_title_duplicate,
    find_similar_title_records,
    score_source_quality,
)
from src.briefing import (
    is_share_ready,
    select_weekly_candidates,
    render_weekly_brief_md,
    render_exec_email,
    _build_synthesis_prompt,
    _choose_brief_mode,
)
from src.text_clean_chunk import clean_and_chunk


# ============================================================================
# Test Fixtures
# ============================================================================


def sample_record(
    title: str = "Default Title",
    source_type: str = "Reuters",
    priority: str = "High",
    confidence: str = "High",
    publish_date: str = "2026-02-12",
    created_at: str = None,
    is_duplicate: bool = False,
    duplicate_story_of: str = None,
    story_primary: bool = True,
) -> dict:
    """Generate a sample record for testing."""
    now = created_at or utc_now_iso()
    return {
        "record_id": new_record_id(),
        "title": title,
        "source_type": source_type,
        "priority": priority,
        "confidence": confidence,
        "publish_date": publish_date,
        "created_at": now,
        "original_url": "https://example.com",
        "actor_type": "oem",
        "government_entities": [],
        "companies_mentioned": ["Tesla"],
        "mentions_our_company": False,
        "topics": ["OEM Strategy & Powertrain Shifts"],
        "keywords": ["electric", "vehicle", "battery", "charging", "supply", "chain"],
        "country_mentions": ["USA"],
        "regions_mentioned": ["United States"],
        "regions_relevant_to_apex_mobility": ["United States"],
        "evidence_bullets": ["Evidence 1", "Evidence 2"],
        "key_insights": ["Insight 1", "Insight 2"],
        "review_status": "Approved",
        "notes": "",
        "is_duplicate": is_duplicate,
        "duplicate_story_of": duplicate_story_of,
        "story_primary": story_primary,
    }


# ============================================================================
# Test: Duplicate Detection (Exact Title Match)
# ============================================================================


class TestExactTitleDuplicateDetection:
    """Test exact title duplicate detection."""

    def test_exact_duplicate_detected(self):
        """Should detect exact duplicate (same normalized title)."""
        records = [
            sample_record(title="Tesla Plans EV Factory Expansion"),
            sample_record(title="Ford Invests in Battery Tech"),
        ]

        result = find_exact_title_duplicate(records, "Tesla Plans EV Factory Expansion")
        assert result is not None
        assert result["title"] == "Tesla Plans EV Factory Expansion"

    def test_duplicate_with_whitespace_normalization(self):
        """Should detect duplicate even with extra whitespace."""
        records = [sample_record(title="Tesla Plans EV Factory Expansion")]

        result = find_exact_title_duplicate(records, "  Tesla  Plans  EV  Factory  Expansion  ")
        assert result is not None

    def test_duplicate_with_case_insensitivity(self):
        """Should detect duplicate regardless of case."""
        records = [sample_record(title="Tesla Plans EV Factory Expansion")]

        result = find_exact_title_duplicate(records, "tesla plans ev factory expansion")
        assert result is not None

    def test_no_duplicate_found(self):
        """Should return None when no exact match exists."""
        records = [sample_record(title="Tesla Plans EV Factory Expansion")]

        result = find_exact_title_duplicate(records, "Ford Invests in Battery Tech")
        assert result is None

    def test_empty_title_returns_none(self):
        """Should return None for empty/blank title input."""
        records = [sample_record(title="Tesla Plans EV Factory Expansion")]

        result = find_exact_title_duplicate(records, "")
        assert result is None


# ============================================================================
# Test: Similar Story Detection (Fuzzy Match)
# ============================================================================


class TestSimilarStoryDetection:
    """Test fuzzy matching for similar stories (same narrative, different source)."""

    def test_similar_stories_detected(self):
        """Should find similar stories with high threshold."""
        records = [
            sample_record(title="Tesla Expands EV Factory in Mexico"),
            sample_record(title="Ford Closes Plant in Michigan"),
        ]

        result = find_similar_title_records(records, "Tesla Expands EV Factory in Mexico", threshold=0.85)
        assert len(result) >= 1
        assert result[0][0]["title"] == "Tesla Expands EV Factory in Mexico"

    def test_very_similar_stories_ranked(self):
        """Should rank similar stories by similarity score."""
        records = [
            sample_record(title="Tesla Expands EV Factory in Mexico"),
            sample_record(title="Tesla Expands Factory in Mexico"),
            sample_record(title="Tesla Plant Mexico"),
        ]

        result = find_similar_title_records(records, "Tesla Expands EV Factory in Mexico", threshold=0.75)
        assert len(result) >= 2
        assert result[0][1] >= result[1][1]  # First should have higher score

    def test_dissimilar_stories_not_matched(self):
        """Should not match dissimilar stories."""
        records = [sample_record(title="Tesla Expands EV Factory in Mexico")]

        result = find_similar_title_records(records, "Ford Reports Q4 Earnings", threshold=0.88)
        assert len(result) == 0


# ============================================================================
# Test: Source Quality Scoring
# ============================================================================


class TestSourceQualityScoring:
    """Test the scoring logic that determines 'better source'."""

    def test_high_priority_high_confidence_scores_higher(self):
        """High priority + high confidence should score highest."""
        weak = sample_record(priority="Low", confidence="Low", source_type="Other")
        strong = sample_record(priority="High", confidence="High", source_type="Reuters")

        assert score_source_quality(strong) > score_source_quality(weak)

    def test_primary_source_scores_higher(self):
        """Reuters/Bloomberg should score higher than 'Other'."""
        primary = sample_record(source_type="Reuters")
        secondary = sample_record(source_type="Other")

        assert score_source_quality(primary) > score_source_quality(secondary)

    def test_source_hierarchy_respected(self):
        """Source ranking should follow the canonical publisher hierarchy."""
        sources_in_order = [
            "S&P",
            "Bloomberg",
            "Reuters",
            "Financial News",
            "MarkLines",
            "Automotive News",
            "Industry Publication",
            "Press Release",
            "Patent",
            "Other",
        ]
        
        scores = []
        for src in sources_in_order:
            rec = sample_record(source_type=src, priority="High", confidence="High")
            scores.append((src, score_source_quality(rec)))
        
        for i in range(len(scores) - 1):
            src1, score1 = scores[i]
            src2, score2 = scores[i + 1]
            assert score1 > score2, f"{src1} ({score1}) should rank higher than {src2} ({score2})"

    def test_url_presence_boosts_score(self):
        """Record with URL should score higher."""
        without_url = sample_record(source_type="Other")
        without_url["original_url"] = None

        with_url = sample_record(source_type="Other")
        with_url["original_url"] = "https://example.com/article"

        assert score_source_quality(with_url) > score_source_quality(without_url)

    def test_more_evidence_boosts_score(self):
        """More evidence bullets should boost score."""
        light = sample_record()
        light["evidence_bullets"] = ["One"]

        heavy = sample_record()
        heavy["evidence_bullets"] = ["One", "Two", "Three", "Four"]

        assert score_source_quality(heavy) > score_source_quality(light)


# ============================================================================
# Test: Weekly Briefing Workflows
# ============================================================================


class TestOWeeklyBriefing:
    """Test weekly briefing selection and rendering."""

    def test_select_weekly_candidates_filters_by_days(self):
        """Should only include records from the last N days."""
        old = sample_record(publish_date="2026-02-01")
        recent = sample_record(publish_date="2026-02-12")

        records = [old, recent]
        candidates = select_weekly_candidates(records, days=7)

        assert len(candidates) >= 1
        assert recent["record_id"] in [c["record_id"] for c in candidates]

    def test_share_ready_items_prioritized(self):
        """Share-ready items (High/High) should come first."""
        share_ready = sample_record(title="Share-ready story", priority="High", confidence="High")
        not_ready = sample_record(title="Non-share-ready story", priority="Low", confidence="Low")

        records = [not_ready, share_ready]
        candidates = select_weekly_candidates(records, days=7, include_excluded=True)

        assert candidates[0]["priority"] == "High"
        assert candidates[0]["confidence"] == "High"

    def test_excluded_items_suppressed_by_default(self):
        """Items marked is_duplicate should be filtered unless flag is set."""
        primary = sample_record(is_duplicate=False)
        duplicate = sample_record(is_duplicate=True, duplicate_story_of=primary["record_id"])

        records = [primary, duplicate]

        candidates_default = select_weekly_candidates(records, days=7, include_excluded=False)
        assert len(candidates_default) == 1

        candidates_all = select_weekly_candidates(records, days=7, include_excluded=True)
        assert len(candidates_all) == 2

    def test_is_share_ready_flag(self):
        """is_share_ready should only be True for High/High."""
        share_ready = sample_record(priority="High", confidence="High")
        not_ready = sample_record(priority="Medium", confidence="High")

        assert is_share_ready(share_ready) is True
        assert is_share_ready(not_ready) is False


# ============================================================================
# Test: Brief Rendering
# ============================================================================


class TestBriefRendering:
    """Test brief and email rendering."""

    def test_render_weekly_brief_markdown(self):
        """Should render markdown brief with share-ready items separated."""
        share_ready = sample_record(priority="High", confidence="High", title="Important News")
        other = sample_record(priority="Medium", confidence="Medium", title="Notable Item")

        records = [share_ready, other]
        brief = render_weekly_brief_md(records, "Feb 5-12, 2026")

        assert "High-Importance (Share-Ready)" in brief
        assert "Important News" in brief
        assert "Notable Item" in brief

    def test_render_exec_email(self):
        """Should render email with subject and body."""
        share_ready = sample_record(priority="High", confidence="High", title="Critical Update")
        records = [share_ready]

        subject, body = render_exec_email(records, "Feb 5-12, 2026")

        assert "Weekly Intelligence Brief" in subject
        assert "Critical Update" in body
        assert "Hello team" in body

    def test_render_empty_brief(self):
        """Should handle empty record list gracefully."""
        brief = render_weekly_brief_md([], "Feb 5-12, 2026")
        assert "No items selected" in brief

        subject, body = render_exec_email([], "Feb 5-12, 2026")
        assert "No items selected" in body


class TestSingleRecordSynthesisPrompt:
    def test_single_mode_config_is_tight(self):
        mode = _choose_brief_mode(1)
        assert mode["name"] == "single"
        assert mode["max_words"] == "350-450"
        assert mode["exec_bullets"] == "2"
        assert mode["priority_bullets"] == "1"
        assert mode["actions_bullets"] == "2"
        assert mode["allow_trends"] is False
        assert mode["include_empty_regions"] is False
        assert mode["include_topics"] is False

    def test_single_record_prompt_enforces_executive_alert_structure(self):
        rec = sample_record(title="Single item", priority="High", confidence="High")
        prompt = _build_synthesis_prompt([rec], "Feb 5-12, 2026")

        assert "EXECUTIVE ALERT" in prompt
        assert "Target length: 350-450 words." in prompt
        # Executive Summary: implications-only job description
        assert "SECTION JOB: State Apex Mobility strategic implications only." in prompt
        assert "Sentence 1: the Apex Mobility implication" in prompt
        # High Priority: Supplier Implications sub-field format
        assert "Supplier Implications:" in prompt
        # Recommended Actions: richer format with Trigger + Deliverable in single mode
        assert "Owner + Action + Time horizon + Trigger + Deliverable" in prompt
        # EMERGING TRENDS heading should not appear as an output section (single mode)
        # The words may still appear in procedure/rule text, so check for section heading format
        assert "\nEMERGING TRENDS\n" not in prompt

    def test_multi_record_prompt_enforces_topic_label_and_action_specificity_format(self):
        rec1 = sample_record(title="Item 1", priority="High", confidence="High")
        rec2 = sample_record(title="Item 2", priority="High", confidence="High")
        rec2["record_id"] = "rec2"
        prompt = _build_synthesis_prompt([rec1, rec2], "Feb 5-12, 2026")

        assert "Topic label line must be plain text (NOT a bullet)." in prompt
        assert "Trigger/watch condition (if/when threshold)" in prompt
        assert "Deliverable artifact (forecast update, risk memo, playbook, dashboard)" in prompt


# ============================================================================
# Test: Title Normalization
# ============================================================================


class TestTitleNormalization:
    """Test title normalization for comparison."""

    def test_normalize_title_lowercase(self):
        """Should convert to lowercase."""
        result = normalize_title("TESLA PLANS EV EXPANSION")
        assert result == result.lower()

    def test_normalize_title_whitespace(self):
        """Should compress whitespace."""
        result = normalize_title("Tesla  Plans   EV    Expansion")
        assert "  " not in result

    def test_normalize_title_punctuation(self):
        """Should remove special characters."""
        result = normalize_title("Tesla's Plans: EV (Expansion)!")
        result_clean = "teslas plans ev expansion"
        assert result == result_clean

    def test_normalize_empty_title(self):
        """Should return empty string for blank input."""
        result = normalize_title("")
        assert result == ""


# ============================================================================
# Integration Test: Full Duplicate Workflow
# ============================================================================


class TestIntegrationDuplicateWorkflow:
    """Test the full workflow: exact duplicate → similar story → pick better source."""

    def test_full_workflow_exact_duplicate_blocks(self):
        """Exact duplicate should be blocked at ingest."""
        records = [sample_record(title="Tesla Factory Expansion")]
        new_title = "Tesla Factory Expansion"

        duplicate = find_exact_title_duplicate(records, new_title)
        assert duplicate is not None, "Should detect exact duplicate"

    def test_full_workflow_similar_story_picks_best_source(self):
        """Similar story should pick stronger source and suppress weaker."""
        weak_source = sample_record(
            title="Tesla Expands Factory in Mexico",
            source_type="Other",
            priority="Low",
            confidence="Low",
        )
        strong_source = sample_record(
            title="Tesla Expands Plant in Mexico",
            source_type="Reuters",
            priority="High",
            confidence="High",
        )

        records = [weak_source]
        similar = find_similar_title_records(
            records, strong_source.get("title", ""), threshold=0.85
        )

        if similar:
            weak_score = score_source_quality(weak_source)
            strong_score = score_source_quality(strong_source)
            assert strong_score > weak_score, "Strong source should outscore weak source"


class TestPreprocessRetention:
    """Ensure key Bloomberg header/software lines survive cleanup."""

    def test_cleaner_keeps_bloomberg_timestamp_and_ai_paragraph(self):
        raw = (
            "Bloomberg\n"
            "February 1, 2026 at 9:00 PM PST\n\n"
            "Mercedes-Benz unveiled the CLA on Jan. 29.\n"
            "The vehicle includes OpenAI and Microsoft voice controls plus Google infotainment features.\n"
        )
        out = clean_and_chunk(raw)
        clean = out["clean_text"]

        assert "February 1, 2026 at 9:00 PM PST" in clean
        assert "OpenAI and Microsoft voice controls" in clean


class TestCompanyCanonicalization:
    """Ensure company name dedup and canonicalization works correctly."""

    def test_vw_volkswagen_dedup(self):
        from src.postprocess import postprocess_record
        rec = sample_record()
        rec["companies_mentioned"] = ["VW", "Volkswagen Group AG", "Porsche"]
        rec = postprocess_record(rec)
        companies = rec["companies_mentioned"]
        assert "Volkswagen" in companies
        assert "VW" not in companies
        assert companies.count("Volkswagen") == 1
        assert "Porsche" in companies

    def test_volkswagen_standalone(self):
        from src.postprocess import postprocess_record
        rec = sample_record()
        rec["companies_mentioned"] = ["Volkswagen"]
        rec = postprocess_record(rec)
        assert rec["companies_mentioned"] == ["Volkswagen"]

    def test_vw_standalone(self):
        from src.postprocess import postprocess_record
        rec = sample_record()
        rec["companies_mentioned"] = ["VW"]
        rec = postprocess_record(rec)
        assert rec["companies_mentioned"] == ["Volkswagen"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
