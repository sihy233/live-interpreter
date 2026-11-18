import numpy as np

from app.audio import Segmenter

SR = 16000
FRAME = SR * 30 // 1000


def make_frame(level: float) -> np.ndarray:
    return np.full(FRAME, level, dtype=np.float32)


def vad(frame: np.ndarray) -> bool:
    return float(np.mean(np.abs(frame))) > 0.05


def feed(segmenter: Segmenter, level: float, count: int) -> list:
    out = []
    for _ in range(count):
        out.extend(segmenter.push(make_frame(level)))
    return out


def test_speech_then_silence_yields_one_segment():
    segmenter = Segmenter(SR, vad)
    assert not feed(segmenter, 0.0, 10)
    assert not feed(segmenter, 0.5, 20)
    segments = feed(segmenter, 0.0, 24)
    assert len(segments) == 1
    assert segments[0].audio.size >= SR * 0.6


def test_short_blip_is_dropped():
    segmenter = Segmenter(SR, vad)
    out = feed(segmenter, 0.0, 5)
    out += feed(segmenter, 0.5, 2)
    out += feed(segmenter, 0.0, 30)
    assert out == []


def test_max_segment_forces_cut():
    segmenter = Segmenter(SR, vad)
    out = feed(segmenter, 0.5, 400)
    assert len(out) == 1
    assert out[0].audio.size <= SR * 10.1
    assert segmenter.active


def test_preroll_is_included():
    segmenter = Segmenter(SR, vad)
    feed(segmenter, 0.0, 10)
    segmenter.push(make_frame(0.5))
    assert segmenter.active
    assert segmenter.current_audio.size >= SR * 0.27


def test_flush_returns_active_segment():
    segmenter = Segmenter(SR, vad)
    feed(segmenter, 0.5, 10)
    segment = segmenter.flush()
    assert segment is not None
    assert segment.audio.size >= SR * 0.3
    assert not segmenter.active
