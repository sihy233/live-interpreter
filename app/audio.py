"""麦克风 / WAV 输入与 VAD 断句。"""

from __future__ import annotations

import queue
import time
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
import webrtcvad

FRAME_MS = 30


@dataclass(frozen=True)
class Segment:
    audio: np.ndarray
    started_at: float
    ended_at: float


class Segmenter:
    def __init__(
        self,
        sample_rate: int,
        is_speech: Callable[[np.ndarray], bool],
        *,
        frame_ms: int = FRAME_MS,
        silence_ms: int = 700,
        max_segment_s: float = 10.0,
        preroll_ms: int = 300,
        min_voiced_ms: int = 200,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * frame_ms // 1000
        self._is_speech = is_speech
        self._silence_frames = silence_ms // frame_ms
        self._max_frames = int(max_segment_s * 1000 / frame_ms)
        self._preroll_frames = preroll_ms // frame_ms
        self._min_voiced_frames = max(1, min_voiced_ms // frame_ms)
        self._reset()

    def _reset(self) -> None:
        self._preroll: deque[np.ndarray] = deque(maxlen=self._preroll_frames)
        self._frames: list[np.ndarray] = []
        self._voiced = 0
        self._silence = 0
        self._started_at = 0.0
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def current_audio(self) -> np.ndarray:
        if not self._frames:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(self._frames)

    @property
    def current_duration_s(self) -> float:
        return len(self._frames) * self.frame_samples / self.sample_rate

    def push(self, frame: np.ndarray) -> list[Segment]:
        frame = np.asarray(frame, dtype=np.float32)
        if frame.size != self.frame_samples:
            raise ValueError(f"帧长度应为 {self.frame_samples}，实际 {frame.size}")
        now = time.monotonic()
        speech = self._is_speech(frame)

        if not self._active:
            self._preroll.append(frame)
            if not speech:
                return []
            self._active = True
            self._frames = list(self._preroll)
            self._voiced = 1
            self._silence = 0
            buffered_s = len(self._frames) * self.frame_samples / self.sample_rate
            self._started_at = now - buffered_s
            return []

        self._frames.append(frame)
        if speech:
            self._voiced += 1
            self._silence = 0
        else:
            self._silence += 1

        if len(self._frames) >= self._max_frames or self._silence >= self._silence_frames:
            segment = self._finish(now)
            return [segment] if segment else []
        return []

    def _finish(self, now: float) -> Segment | None:
        segment = None
        if self._frames and self._voiced >= self._min_voiced_frames:
            segment = Segment(
                audio=np.concatenate(self._frames),
                started_at=self._started_at,
                ended_at=now,
            )
        self._reset()
        return segment

    def flush(self) -> Segment | None:
        if not self._active:
            return None
        return self._finish(time.monotonic())


class Vad:
    def __init__(self, sample_rate: int, aggressiveness: int = 2) -> None:
        self.sample_rate = sample_rate
        self._vad = webrtcvad.Vad(aggressiveness)

    def __call__(self, frame: np.ndarray) -> bool:
        pcm = (np.clip(frame, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        return self._vad.is_speech(pcm, self.sample_rate)


class MicSource:
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = FRAME_MS,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * frame_ms // 1000
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._buffer = np.empty(0, dtype=np.float32)
        self._stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_samples,
            device=device,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status) -> None:
        self._queue.put(indata[:, 0].copy())

    def __enter__(self) -> "MicSource":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def read_frame(self) -> np.ndarray:
        while self._buffer.size < self.frame_samples:
            chunk = self._queue.get().astype(np.float32) / 32768.0
            self._buffer = np.concatenate([self._buffer, chunk])
        frame = self._buffer[: self.frame_samples]
        self._buffer = self._buffer[self.frame_samples :]
        return frame


class SystemSource:
    """WASAPI 系统音频回环：捕获扬声器正在播放的声音。"""

    def __init__(self, sample_rate: int = 16000, frame_ms: int = FRAME_MS) -> None:
        import soundcard as sc

        speaker = sc.default_speaker()
        if speaker is None:
            raise RuntimeError("没有找到默认扬声器，无法捕获系统音频")
        self.speaker_name = speaker.name
        try:
            mic = sc.get_microphone(str(speaker.name), include_loopback=True)
        except Exception as exc:
            names = ", ".join(s.name for s in sc.all_speakers())
            raise RuntimeError(
                f"无法打开默认扬声器的回环设备：{exc}\n可用扬声器：{names}"
            ) from exc
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * frame_ms // 1000
        self._recorder = mic.recorder(
            samplerate=sample_rate,
            channels=1,
            blocksize=self.frame_samples,
        )

    def __enter__(self) -> "SystemSource":
        self._recorder.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._recorder.__exit__(*exc)

    def read_frame(self) -> np.ndarray:
        data = self._recorder.record(numframes=self.frame_samples)
        data = np.asarray(data, dtype=np.float32).reshape(-1)
        if data.size < self.frame_samples:
            data = np.pad(data, (0, self.frame_samples - data.size))
        return data[: self.frame_samples]


class WavSource:
    def __init__(
        self,
        path: Path,
        sample_rate: int = 16000,
        frame_ms: int = FRAME_MS,
        *,
        realtime: bool = True,
    ) -> None:
        self._wav = wave.open(str(path), "rb")
        if self._wav.getnchannels() != 1 or self._wav.getsampwidth() != 2:
            raise ValueError("WAV 必须是单声道 16-bit")
        if self._wav.getframerate() != sample_rate:
            raise ValueError(f"WAV 采样率必须是 {sample_rate}Hz")
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * frame_ms // 1000
        self._realtime = realtime
        self._start = time.monotonic()
        self._frames_read = 0

    def __enter__(self) -> "WavSource":
        return self

    def __exit__(self, *exc) -> None:
        self._wav.close()

    def read_frame(self) -> np.ndarray:
        raw = self._wav.readframes(self.frame_samples)
        if not raw:
            raise EOFError
        if self._realtime:
            target = self._start + self._frames_read * self.frame_samples / self.sample_rate
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        self._frames_read += 1
        pcm = np.frombuffer(raw, dtype=np.int16)
        if pcm.size < self.frame_samples:
            pcm = np.pad(pcm, (0, self.frame_samples - pcm.size))
        return pcm.astype(np.float32) / 32768.0
