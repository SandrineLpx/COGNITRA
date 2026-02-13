from __future__ import annotations

import sys
from pathlib import Path

from src.text_clean_chunk import clean_and_chunk


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_clean_chunk.py <text-file>")
        return

    path = Path(sys.argv[1])
    raw = path.read_text(encoding="utf-8", errors="ignore")
    out = clean_and_chunk(raw)
    meta = out["meta"]
    chunks = out["chunks"]

    print("META:")
    print(meta)
    print("\nCLEAN PREVIEW:")
    print(out["clean_text"][:500])

    for i, ch in enumerate(chunks, 1):
        print(f"\n--- CHUNK {i}/{len(chunks)} ---")
        print(ch[:500])


if __name__ == "__main__":
    main()
