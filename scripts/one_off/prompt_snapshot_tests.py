"""
Snapshot tests for synthesis prompt structure.

These tests assert exact prompt wording from a specific iteration.
They are NOT part of the CI suite because the prompt evolves with each iteration.
Run manually to verify prompt structure after prompt changes:

    python -m pytest scripts/one_off/prompt_snapshot_tests.py -v

Last validated against: v4.9 prompt iteration (2026-02-16).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests.test_scenarios import sample_record
from src.briefing import _build_synthesis_prompt, _choose_brief_mode


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
        assert "SECTION JOB: State Apex Mobility strategic implications only." in prompt
        assert "Sentence 1: the Apex Mobility implication" in prompt
        assert "Supplier Implications:" in prompt
        assert "Owner + Action + Time horizon + Trigger + Deliverable" in prompt
        assert "\nEMERGING TRENDS\n" not in prompt

    def test_multi_record_prompt_enforces_topic_label_and_action_specificity_format(self):
        rec1 = sample_record(title="Item 1", priority="High", confidence="High")
        rec2 = sample_record(title="Item 2", priority="High", confidence="High")
        rec2["record_id"] = "rec2"
        prompt = _build_synthesis_prompt([rec1, rec2], "Feb 5-12, 2026")

        assert "Topic label line must be plain text (NOT a bullet)." in prompt
        assert "Trigger/watch condition (if/when threshold)" in prompt
        assert "Deliverable artifact (forecast update, risk memo, playbook, dashboard)" in prompt
