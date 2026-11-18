"""播放测试 WAV，并从系统音频回环识别，验证 WASAPI loopback 是否工作。"""

import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.asr import Transcriber
from app.audio import Segmenter, SystemSource, Vad

WAV = Path(__file__).resolve().parent.parent / "samples" / "test16.wav"


def main() -> None:
    with wave.open(str(WAV), "rb") as w:
        sample_rate = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        audio = audio.astype(np.float32) / 32768.0

    print("加载 ASR ...", flush=True)
    transcriber = Transcriber()

    def play() -> None:
        time.sleep(0.5)
        sd.play(audio, sample_rate)
        sd.wait()
        print("播放结束", flush=True)

    threading.Thread(target=play, daemon=True).start()

    segmenter = Segmenter(sample_rate, Vad(sample_rate))
    segments = []
    with SystemSource(sample_rate=sample_rate) as source:
        deadline = time.monotonic() + 14
        while time.monotonic() < deadline:
            segments.extend(segmenter.push(source.read_frame()))
    tail = segmenter.flush()
    if tail is not None:
        segments.append(tail)

    print(f"分段数：{len(segments)}", flush=True)
    for segment in segments:
        print("EN:", transcriber.final(segment.audio), flush=True)


if __name__ == "__main__":
    main()
