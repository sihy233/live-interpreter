"""本地英文语音 → 中文双语字幕。"""

from __future__ import annotations

import argparse
import atexit
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import truststore

truststore.inject_into_ssl()

from app.asr import Transcriber  # noqa: E402
from app.audio import MicSource, Segmenter, SystemSource, Vad, WavSource  # noqa: E402
from app.mt import Translator  # noqa: E402
from app.overlay import Overlay  # noqa: E402
from app.runtime import OllamaRuntime  # noqa: E402
from app.transcript import TranscriptWriter  # noqa: E402
from app.ui import UI  # noqa: E402

SAMPLE_RATE = 16000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地英文→中文同声传译")
    parser.add_argument("--wav", type=Path, help="用 16kHz 单声道 WAV 代替麦克风")
    parser.add_argument("--no-realtime", action="store_true", help="WAV 不按实时速度播放")
    parser.add_argument("--device", help="麦克风序号或名称")
    parser.add_argument(
        "--source",
        choices=["mic", "system"],
        default="mic",
        help="mic=麦克风，system=系统音频回环（会议/视频）",
    )
    parser.add_argument("--overlay", action="store_true", help="显示置顶字幕浮窗")
    parser.add_argument("--overlay-font-size", type=int, default=28, help="浮窗中文字号")
    parser.add_argument("--overlay-opacity", type=float, default=0.85, help="浮窗不透明度 0.2-1.0")
    parser.add_argument(
        "--overlay-position",
        choices=["bottom", "top"],
        default="bottom",
        help="浮窗位置",
    )
    parser.add_argument("--overlay-no-english", action="store_true", help="浮窗只显示中文")
    parser.add_argument("--asr-model", default="large-v3-turbo")
    parser.add_argument(
        "--asr-device",
        choices=["cuda", "cpu"],
        default="cuda",
        help="ASR 推理设备；无 NVIDIA GPU 时用 cpu + small.en",
    )
    parser.add_argument("--mt-model", default="hunyuan-mt-7b")
    parser.add_argument("--out-dir", type=Path, default=PROJECT / "transcripts")
    return parser.parse_args()


class App:
    def __init__(
        self,
        transcriber: Transcriber,
        translator: Translator,
        writer: TranscriptWriter,
        ui: UI,
        source: MicSource | SystemSource | WavSource,
    ) -> None:
        self.transcriber = transcriber
        self.translator = translator
        self.writer = writer
        self.ui = ui
        self.source = source
        self.segmenter = Segmenter(SAMPLE_RATE, Vad(SAMPLE_RATE))
        self.final_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._generation = 0
        self._partial_busy = False
        self._final_thread = threading.Thread(target=self._final_loop, daemon=True)

    def run(self) -> None:
        self._final_thread.start()
        self.ui.start()
        last_partial = 0.0
        last_refresh = 0.0
        try:
            with self.source:
                while True:
                    frame = self.source.read_frame()
                    segments = self.segmenter.push(frame)
                    now = time.monotonic()

                    if self.segmenter.active and now - last_partial >= 0.6:
                        last_partial = now
                        self._submit_partial()

                    for segment in segments:
                        self._enqueue(segment, now)

                    if now - last_refresh >= 0.1:
                        last_refresh = now
                        self.ui.refresh()
        except EOFError:
            pass
        finally:
            self._enqueue(self.segmenter.flush(), time.monotonic())
            self.final_queue.put(None)
            self._final_thread.join(timeout=15)
            self.ui.refresh()
            self.ui.stop()

    def _enqueue(self, segment, now: float) -> None:
        if segment is None:
            return
        with self._lock:
            self._generation += 1
        self.ui.clear_partial()
        started = datetime.now() - timedelta(seconds=now - segment.started_at)
        self.final_queue.put((segment, started, datetime.now()))

    def _submit_partial(self) -> None:
        if self._partial_busy:
            return
        audio = self.segmenter.current_audio
        if audio.size < SAMPLE_RATE * 0.3:
            return
        with self._lock:
            generation = self._generation
        self._partial_busy = True
        threading.Thread(
            target=self._partial_work,
            args=(audio, generation),
            daemon=True,
        ).start()

    def _partial_work(self, audio, generation: int) -> None:
        try:
            en = self.transcriber.partial(audio)
            if not en:
                return
            with self._lock:
                if generation != self._generation:
                    return
            self.ui.set_partial_en(en)

            zh = self.translator.translate(en)
            if not zh:
                return
            with self._lock:
                if generation != self._generation:
                    return
            self.ui.set_partial_zh(zh)
        except Exception as exc:
            print(f"partial 失败：{exc}", flush=True)
            self.ui.set_status(f"partial 失败：{exc}")
        finally:
            self._partial_busy = False

    def _final_loop(self) -> None:
        while True:
            item = self.final_queue.get()
            if item is None:
                return
            segment, started, ended = item
            try:
                t0 = time.monotonic()
                en = self.transcriber.final(segment.audio)
                t1 = time.monotonic()
                if not en:
                    continue
                zh = self.translator.translate(en)
                t2 = time.monotonic()
                if not zh:
                    self.ui.set_status("翻译返回空结果")
                    continue
                self.writer.commit(en, zh, started, ended)
                self.ui.commit(ended, en, zh)
                self.ui.set_status(
                    f"ASR {t1 - t0:.1f}s · MT {t2 - t1:.1f}s · 处理 {t2 - t0:.1f}s"
                )
            except Exception as exc:
                print(f"处理失败：{exc}", flush=True)
                self.ui.set_status(f"处理失败：{exc}")


def main() -> int:
    args = parse_args()
    runtime = OllamaRuntime(PROJECT)
    atexit.register(runtime.close)
    try:
        print("启动私有 Ollama ...", flush=True)
        host = runtime.start()
        if not runtime.has_model(args.mt_model):
            raise RuntimeError(
                f"找不到翻译模型 {args.mt_model}，请先运行：uv run python setup.py"
            )
        print(f"Ollama: {host}", flush=True)

        print("加载翻译模型 ...", flush=True)
        translator = Translator(args.mt_model, host)
        translator.warmup()

        print("加载 ASR 模型 ...", flush=True)
        transcriber = Transcriber(
            args.asr_model,
            device=args.asr_device,
            compute_type="int8_float16" if args.asr_device == "cuda" else "int8",
        )

        writer = TranscriptWriter(args.out_dir)
        print(f"记录文件：{writer.jsonl_path}", flush=True)
        print(f"          {writer.md_path}", flush=True)

        if args.wav:
            source = WavSource(args.wav, realtime=not args.no_realtime)
        elif args.source == "system":
            if args.device:
                print("提示：--device 只对麦克风模式生效，系统音频模式已忽略。", flush=True)
            print("音源：系统音频回环（默认扬声器）", flush=True)
            source = SystemSource()
        else:
            import sounddevice as sd

            info = (
                sd.query_devices(args.device, kind="input")
                if args.device
                else sd.query_devices(kind="input")
            )
            print(f"麦克风：{info['name']}（#{info['index']}）", flush=True)
            source = MicSource(device=args.device)

        overlay = None
        if args.overlay:
            overlay = Overlay(
                font_size=args.overlay_font_size,
                opacity=args.overlay_opacity,
                position=args.overlay_position,
                show_english=not args.overlay_no_english,
            )

        print("开始监听（Ctrl+C 退出）...", flush=True)
        App(
            transcriber,
            translator,
            writer,
            UI(args.asr_model, args.mt_model, overlay=overlay),
            source,
        ).run()
        print("\n已停止。", flush=True)
        return 0
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
        return 0
    except Exception as exc:
        print(f"\n运行失败：{exc}", flush=True)
        return 1
    finally:
        runtime.close()
        atexit.unregister(runtime.close)


if __name__ == "__main__":
    raise SystemExit(main())
