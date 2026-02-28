from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import shutil
import uuid

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RECORDS_PATH = DATA_DIR / "records.jsonl"
PDF_DIR = DATA_DIR / "pdfs"
BRIEFS_DIR = DATA_DIR / "briefs"
BRIEF_INDEX = BRIEFS_DIR / "index.jsonl"
DEMO_SEED_DIR = DATA_DIR / "demo_seed"
DEMO_BASELINE_RECORDS = DEMO_SEED_DIR / "records_baseline.jsonl"
DEMO_SEED_BRIEFS_DIR = DEMO_SEED_DIR / "briefs"

def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

def _jsonl_has_rows(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    return True
    except OSError:
        return False
    return False

def _bootstrap_demo_seed_if_needed() -> None:
    # Auto-seed demo data only when live records are empty or missing.
    if _jsonl_has_rows(RECORDS_PATH):
        return
    if not DEMO_BASELINE_RECORDS.exists():
        return
    try:
        shutil.copyfile(DEMO_BASELINE_RECORDS, RECORDS_PATH)
    except OSError:
        return

    # Seed saved briefs only when the target brief store is still empty.
    if not DEMO_SEED_BRIEFS_DIR.exists():
        return
    try:
        has_live_briefs = any(BRIEFS_DIR.glob("brief_*.md"))
        has_live_index = _jsonl_has_rows(BRIEF_INDEX)
    except OSError:
        return
    if has_live_briefs or has_live_index:
        return

    try:
        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        for pattern in ("brief_*.md", "brief_*.meta.json"):
            for src in DEMO_SEED_BRIEFS_DIR.glob(pattern):
                dst = BRIEFS_DIR / src.name
                if not dst.exists():
                    shutil.copyfile(src, dst)
        src_index = DEMO_SEED_BRIEFS_DIR / "index.jsonl"
        if src_index.exists() and not BRIEF_INDEX.exists():
            shutil.copyfile(src_index, BRIEF_INDEX)
    except OSError:
        return

def new_record_id() -> str:
    return uuid.uuid4().hex[:12]

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def append_record(record: dict) -> None:
    ensure_dirs()
    with RECORDS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def load_records() -> list[dict]:
    ensure_dirs()
    _bootstrap_demo_seed_if_needed()
    if not RECORDS_PATH.exists():
        return []
    rows = []
    with RECORDS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows

def overwrite_records(records: list[dict]) -> None:
    ensure_dirs()
    with RECORDS_PATH.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def save_pdf_bytes(record_id: str, pdf_bytes: bytes, filename: str) -> str:
    ensure_dirs()
    safe_name = "".join(c for c in filename if c.isalnum() or c in ("-", "_", ".", " ")).strip() or "source.pdf"
    path = PDF_DIR / f"{record_id}__{safe_name}"
    path.write_bytes(pdf_bytes)
    return str(path)
