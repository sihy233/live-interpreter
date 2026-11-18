"""Hunyuan-MT 英译中客户端。"""

from __future__ import annotations

from ollama import Client

PROMPT = (
    "Translate the following segment into Chinese, "
    "without additional explanation.\n\n{text}"
)


def build_prompt(text: str) -> str:
    return PROMPT.format(text=text.strip())


def clean_translation(text: str) -> str:
    text = text.strip()
    for prefix in ("Chinese:", "Chinese：", "中文：", "中文:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text.strip().strip('"“”').strip()


class Translator:
    def __init__(self, model: str, host: str) -> None:
        self.model = model
        self.client = Client(host=host, timeout=30)

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": build_prompt(text)}],
            options={"temperature": 0.1, "top_p": 0.6, "num_predict": 256},
            keep_alive=-1,
        )
        return clean_translation(response.message.content or "")

    def warmup(self) -> None:
        self.translate("Hello.")
