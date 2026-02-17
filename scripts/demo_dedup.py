from __future__ import annotations

from pprint import pprint

from src.dedupe import dedup_and_rank


def main() -> None:
    records = [
        {
            "record_id": "r1",
            "title": "Ford and Geely expand EV plant capacity in Valencia, report says",
            "source_type": "S&P",
            "publish_date": "2026-02-11",
            "publish_date_confidence": "High",
            "companies_mentioned": ["Ford", "Geely"],
            "topics": ["Supply Chain & Manufacturing", "Market & Competition"],
            "evidence_bullets": [
                "Ford and Geely expanded Valencia capacity amid tariff pressure.",
                "The update cited higher EV demand and supplier adjustments.",
            ],
            "keywords": ["ford", "geely", "valencia", "capacity", "tariff"],
            "original_url": "https://example.com/sp_story",
            "created_at": "2026-02-11T08:00:00+00:00",
        },
        {
            "record_id": "r2",
            "title": "Ford and Geely expand EV plant capacity in Valencia",
            "source_type": "Reuters",
            "publish_date": "2026-02-11",
            "publish_date_confidence": "Medium",
            "companies_mentioned": ["Ford", "Geely"],
            "topics": ["Supply Chain & Manufacturing"],
            "evidence_bullets": [
                "Ford and Geely are discussing production expansion.",
                "Capacity in Valencia may increase this year.",
            ],
            "keywords": ["ford", "geely", "production", "valencia", "expansion"],
            "original_url": "https://example.com/reuters_story",
            "created_at": "2026-02-11T09:00:00+00:00",
        },
        {
            "record_id": "r3",
            "title": "NHTSA opens recall investigation into EV charging faults",
            "source_type": "Automotive News",
            "publish_date": "2026-02-10",
            "publish_date_confidence": "High",
            "companies_mentioned": ["Ford"],
            "topics": ["Regulatory & Safety"],
            "evidence_bullets": [
                "NHTSA opened a safety probe on charging faults.",
                "The issue affects multiple EV model years.",
            ],
            "keywords": ["nhtsa", "recall", "ev", "safety", "ford"],
            "original_url": "https://example.com/an_story",
            "created_at": "2026-02-10T10:00:00+00:00",
        },
    ]

    kept, excluded = dedup_and_rank(records)
    print("KEPT:")
    pprint([{k: r.get(k) for k in ("record_id", "source_type", "dedup_cluster_size", "dedup_sources")} for r in kept])
    print("\nEXCLUDED:")
    pprint([{k: r.get(k) for k in ("record_id", "canonical_record_id", "dedup_reason")} for r in excluded])


if __name__ == "__main__":
    main()
