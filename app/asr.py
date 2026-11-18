"""faster-whisper 流式识别封装。"""

from __future__ import annotations

import os
import site
import threading
from pathlib import Path

import numpy as np

# CTranslate2 在 Windows 上从 PATH 找 CUDA 12 的 cublas/cudnn DLL。
# cuBLAS/cuDART 直接复用便携 Ollama 自带的 CUDA 12 运行时，cuDNN 来自 pip 包。
_DLL_DIRS = []
_project = Path(__file__).resolve().parent.parent
for _dir in (
    _project / "tools" / "cudnn" / "bin",
    _project / "tools" / "ollama" / "lib" / "ollama" / "cuda_v12",
):
    if _dir.is_dir():
        _DLL_DIRS.append(os.add_dll_directory(str(_dir)))
        os.environ["PATH"] = str(_dir) + os.pathsep + os.environ.get("PATH", "")
for _site in site.getsitepackages():
    for _bin in (Path(_site) / "nvidia").glob("*/bin"):
        if _bin.is_dir():
            _DLL_DIRS.append(os.add_dll_directory(str(_bin)))
            os.environ["PATH"] = str(_bin) + os.pathsep + os.environ.get("PATH", "")

from faster_whisper import WhisperModel  # noqa: E402

ARTIFACTS = {"[BLANK_AUDIO]", "[blank_audio]", "(silence)", "[silence]", "..."}


def clean_transcript(text: str) -> str:
    text = " ".join(text.split()).strip()
    return "" if text in ARTIFACTS else text


class Transcriber:
    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "int8_float16",
    ) -> None:
        try:
            self.model = WhisperModel(
                model_size, device=device, compute_type=compute_type
            )
        except Exception as exc:
            raise RuntimeError(
                f"ASR 模型加载失败（device={device}, compute_type={compute_type}）：{exc}"
            ) from exc
        self._lock = threading.Lock()

    def _transcribe(self, audio: np.ndarray, beam_size: int) -> str:
        with self._lock:
            segments, _ = self.model.transcribe(
                audio.astype(np.float32),
                language="en",
                beam_size=beam_size,
                best_of=beam_size,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=False,
                without_timestamps=True,
            )
            text = " ".join(segment.text.strip() for segment in segments)
        return clean_transcript(text)

    def partial(self, audio: np.ndarray) -> str:
        return self._transcribe(audio, beam_size=1)

    def final(self, audio: np.ndarray) -> str:
        return self._transcribe(audio, beam_size=5)
