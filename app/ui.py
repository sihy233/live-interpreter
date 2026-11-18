"""Rich 终端双语界面。"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.rule import Rule
from rich.text import Text

if TYPE_CHECKING:
    from app.overlay import Overlay


class UI:
    def __init__(
        self,
        asr_model: str,
        mt_model: str,
        console: Console | None = None,
        overlay: "Overlay | None" = None,
    ) -> None:
        self.console = console or Console()
        self.asr_model = asr_model
        self.mt_model = mt_model
        self.overlay = overlay
        self._lock = threading.Lock()
        self._committed: deque[tuple[datetime, str, str]] = deque(maxlen=6)
        self._partial_en = ""
        self._partial_zh = ""
        self._status = "启动中…"
        self._count = 0
        self._live: Live | None = None

    def start(self) -> None:
        if self.overlay is not None:
            self.overlay.start()
        if not self.console.is_terminal:
            return
        self._live = Live(
            self.render(),
            console=self.console,
            auto_refresh=False,
            transient=False,
        )
        self._live.start(refresh=True)

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        if self.overlay is not None:
            self.overlay.stop()

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render(), refresh=True)

    def commit(self, at: datetime, en: str, zh: str) -> None:
        with self._lock:
            self._committed.append((at, en, zh))
            self._count += 1
        if self.overlay is not None:
            self.overlay.commit(en, zh)
        if not self.console.is_terminal:
            print(f"[{at:%H:%M:%S}] {en}\n           {zh}", flush=True)

    def clear_partial(self) -> None:
        with self._lock:
            self._partial_en = ""
            self._partial_zh = ""
        if self.overlay is not None:
            self.overlay.clear_partial()

    def set_partial_en(self, text: str) -> None:
        with self._lock:
            self._partial_en = text
        if self.overlay is not None:
            self.overlay.set_partial(en=text)

    def set_partial_zh(self, text: str) -> None:
        with self._lock:
            self._partial_zh = text
        if self.overlay is not None:
            self.overlay.set_partial(zh=text)

    def set_status(self, text: str) -> None:
        with self._lock:
            self._status = text

    def render(self) -> RenderableType:
        with self._lock:
            committed = list(self._committed)
            partial_en = self._partial_en
            partial_zh = self._partial_zh
            status = self._status
            count = self._count

        lines: list[RenderableType] = [
            Text("Live Interpreter   EN → 中文", style="bold cyan"),
            Rule(style="cyan"),
        ]
        for at, en, zh in committed:
            lines.append(Text.assemble((f"[{at:%H:%M:%S}] ", "dim"), (en, "white")))
            lines.append(Text.assemble(("           ", ""), (zh, "bold green")))

        if partial_en or partial_zh:
            lines.append(Rule(style="dim"))
            lines.append(Text.assemble(("EN~ ", "dim"), (partial_en, "grey62")))
            lines.append(Text.assemble(("ZH~ ", "yellow"), (partial_zh, "yellow")))

        lines.append(Rule(style="dim"))
        lines.append(
            Text(
                f"{self.asr_model} · {self.mt_model} · 已记录 {count} 句 · "
                f"{status} · Ctrl+C 退出",
                style="dim",
            )
        )
        return Group(*lines)
