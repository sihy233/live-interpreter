import json
from datetime import datetime

from app.transcript import TranscriptWriter


def test_commit_writes_jsonl_and_markdown(tmp_path):
    writer = TranscriptWriter(tmp_path, now=datetime(2026, 11, 18, 14, 30))
    writer.commit(
        "Hello.",
        "你好。",
        datetime(2026, 11, 18, 14, 30, 1),
        datetime(2026, 11, 18, 14, 30, 2),
    )

    assert writer.jsonl_path.name == "2026-11-18_143000.jsonl"
    record = json.loads(writer.jsonl_path.read_text(encoding="utf-8").strip())
    assert record == {
        "started_at": "2026-11-18T14:30:01",
        "ended_at": "2026-11-18T14:30:02",
        "en": "Hello.",
        "zh": "你好。",
    }

    markdown = writer.md_path.read_text(encoding="utf-8")
    assert "**EN:** Hello." in markdown
    assert "**ZH:** 你好。" in markdown
