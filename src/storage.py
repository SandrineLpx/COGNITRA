from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RECORDS_PATH = DATA_DIR / "records.jsonl"
PDF_DIR = DATA_DIR / "pdfs"

def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

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
