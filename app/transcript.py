"""把每句原文和译文追加到 JSONL 与 Markdown。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class TranscriptWriter:
    def __init__(self, out_dir: Path, now: datetime | None = None) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        session = now or datetime.now()
        stem = session.strftime("%Y-%m-%d_%H%M%S")
        self.jsonl_path = self.out_dir / f"{stem}.jsonl"
        self.md_path = self.out_dir / f"{stem}.md"
        self.md_path.write_text(
            f"# Live Interpreter — {session:%Y-%m-%d %H:%M}\n\n",
            encoding="utf-8",
        )

    def commit(
        self,
        en: str,
        zh: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        record = {
            "started_at": started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "en": en,
            "zh": zh,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        with self.md_path.open("a", encoding="utf-8") as f:
            f.write(
                f"## {ended_at:%H:%M:%S}\n\n"
                f"**EN:** {en}\n\n"
                f"**ZH:** {zh}\n\n"
            )
