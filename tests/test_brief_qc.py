from src.quality import run_brief_qc


def _run_brief_qc(brief_text: str, selected_ids: list[str]):
    findings, metrics = run_brief_qc(
        run_id="qc_test",
        run_version=1,
        brief_id="brief_test",
        brief_text=brief_text,
        selected_record_ids=selected_ids,
        selected_records=[],
    )
    return findings, metrics


def test_topic_label_bullet_is_not_flagged_as_ungrounded_claim():
    brief_text = (
        "EXECUTIVE SUMMARY\n"
        "- Demand softened in Europe (REC:abc123)\n\n"
        "KEY DEVELOPMENTS BY TOPIC\n"
        "* **OEM Strategy & Powertrain Shifts**\n"
        "- EV rollout timing shifted for multiple OEMs (REC:abc123)\n\n"
        "RECOMMENDED ACTIONS\n"
        "- VP Sales updates risk memo this quarter (REC:abc123)\n"
    )
    findings, _metrics = _run_brief_qc(brief_text, ["abc123"])

    assert not any(
        f.get("issue_type") == "ungrounded_claim"
        and "OEM Strategy & Powertrain Shifts" in str(f.get("claim_text") or "")
        for f in findings
    )


def test_uncited_topic_claim_bullet_is_still_flagged():
    brief_text = (
        "EXECUTIVE SUMMARY\n"
        "- Demand softened in Europe (REC:abc123)\n\n"
        "KEY DEVELOPMENTS BY TOPIC\n"
        "* OEM strategy shifts accelerated across Europe\n"
        "- EV rollout timing shifted for multiple OEMs (REC:abc123)\n"
    )
    findings, _metrics = _run_brief_qc(brief_text, ["abc123"])

    assert any(
        f.get("issue_type") == "ungrounded_claim"
        and "OEM strategy shifts accelerated across Europe" in str(f.get("claim_text") or "")
        for f in findings
    )


def test_invalid_rec_id_is_flagged_as_mismatch():
    brief_text = (
        "EXECUTIVE SUMMARY\n"
        "- Demand softened in Europe (REC:abc123)\n\n"
        "EMERGING TRENDS\n"
        "- Divergent electrification timelines are widening (REC:bad999)\n"
    )
    findings, _metrics = _run_brief_qc(brief_text, ["abc123"])

    assert any(f.get("issue_type") == "rec_mismatch" for f in findings)
