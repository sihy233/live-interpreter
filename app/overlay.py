"""置顶、点击穿透的双语字幕浮窗。"""

from __future__ import annotations

import ctypes
import queue
import threading
import tkinter as tk
from dataclasses import dataclass

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080


@dataclass
class SubtitleState:
    show_english: bool = True
    final_en: str = ""
    final_zh: str = ""
    partial_en: str = ""
    partial_zh: str = ""

    def commit(self, en: str, zh: str) -> None:
        self.final_en = en
        self.final_zh = zh
        self.partial_en = ""
        self.partial_zh = ""

    def clear_partial(self) -> None:
        self.partial_en = ""
        self.partial_zh = ""

    def set_partial_en(self, text: str) -> None:
        self.partial_en = text

    def set_partial_zh(self, text: str) -> None:
        self.partial_zh = text

    def display(self) -> tuple[str, str]:
        en = self.partial_en or self.final_en
        zh = self.partial_zh or self.final_zh
        return (en if self.show_english else ""), zh


class Overlay:
    """Tk 必须运行在创建它的线程里，其他线程只通过队列投递文本。"""

    def __init__(
        self,
        font_size: int = 28,
        opacity: float = 0.85,
        position: str = "bottom",
        show_english: bool = True,
    ) -> None:
        self.state = SubtitleState(show_english=show_english)
        self.font_size = font_size
        self.opacity = max(0.2, min(1.0, opacity))
        self.position = position
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._root: tk.Tk | None = None
        self._hwnd: int | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="overlay", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("字幕浮窗启动超时")
        if self._error is not None:
            raise RuntimeError(f"字幕浮窗启动失败：{self._error}")

    def stop(self) -> None:
        if self._thread is None:
            return
        self._queue.put(("quit", None))
        self._thread.join(timeout=3)
        self._thread = None

    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    def commit(self, en: str, zh: str) -> None:
        self._queue.put(("commit", (en, zh)))

    def clear_partial(self) -> None:
        self._queue.put(("clear", None))

    def set_partial(self, en: str | None = None, zh: str | None = None) -> None:
        self._queue.put(("partial", (en, zh)))

    def _run(self) -> None:
        try:
            root = tk.Tk()
            self._root = root
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-alpha", self.opacity)
            root.configure(bg="black")

            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            width = int(screen_w * 0.9)
            height = max(140, self.font_size * 4 + 50)
            x = (screen_w - width) // 2
            y = screen_h - height - 80 if self.position == "bottom" else 60
            root.geometry(f"{width}x{height}+{x}+{y}")

            family = "Microsoft YaHei UI"
            en_var = tk.StringVar()
            zh_var = tk.StringVar()
            en_label = tk.Label(
                root,
                textvariable=en_var,
                fg="#b8b8b8",
                bg="black",
                font=(family, max(10, self.font_size // 2)),
                wraplength=width - 60,
                justify="center",
            )
            zh_label = tk.Label(
                root,
                textvariable=zh_var,
                fg="white",
                bg="black",
                font=(family, self.font_size, "bold"),
                wraplength=width - 60,
                justify="center",
            )
            if self.state.show_english:
                en_label.pack(side="top", pady=(10, 0))
            zh_label.pack(side="top", pady=(4, 10))

            self._hwnd = self._make_click_through(root)
            root.update()
            root.lift()
            root.attributes("-topmost", True)
            root.after(50, self._poll, en_var, zh_var)
            self._ready.set()
            root.mainloop()
        except Exception as exc:  # Tk 失败要让主程序知道，不能静默
            self._error = exc
            self._ready.set()
        finally:
            self._root = None

    def _poll(self, en_var: tk.StringVar, zh_var: tk.StringVar) -> None:
        changed = False
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == "quit":
                if self._root is not None:
                    self._root.destroy()
                return
            if kind == "commit":
                self.state.commit(*payload)
            elif kind == "clear":
                self.state.clear_partial()
            elif kind == "partial":
                en, zh = payload
                if en is not None:
                    self.state.set_partial_en(en)
                if zh is not None:
                    self.state.set_partial_zh(zh)

        if changed:
            en, zh = self.state.display()
            en_var.set(en)
            zh_var.set(zh)
        if self._root is not None:
            self._root.after(50, self._poll, en_var, zh_var)

    @staticmethod
    def _make_click_through(root: tk.Tk) -> int:
        root.update_idletasks()
        hwnd = root.winfo_id()
        user32 = ctypes.windll.user32
        parent = user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
        )
        return hwnd
