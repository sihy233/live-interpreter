"""一次性初始化：下载便携 Ollama、翻译模型、ASR 模型。"""

from __future__ import annotations

import os
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import truststore

truststore.inject_into_ssl()

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from app.runtime import OllamaRuntime

PROJECT = Path(__file__).resolve().parent
TOOLS = PROJECT / "tools"
MODELS = PROJECT / "models"
MARKER = TOOLS / ".ready"

OLLAMA_ZIP = TOOLS / "ollama-windows-amd64.zip"
OLLAMA_URL = (
    "https://github.com/ollama/ollama/releases/download/v0.40.16/"
    "ollama-windows-amd64.zip"
)
GGUF = MODELS / "Hunyuan-MT-7B-q4_k_m.gguf"
GGUF_URL = (
    "https://hf-mirror.com/Mungert/Hunyuan-MT-7B-GGUF/resolve/main/"
    "Hunyuan-MT-7B-q4_k_m.gguf"
)
CUDNN_WHEEL = TOOLS / "cudnn-win.whl"
CUDNN_URL = (
    "https://files.pythonhosted.org/packages/c7/bd/"
    "1d6709d2223e99f04079f16005f8ae6e11a14ee16b5eab6833686cf72fe1/"
    "nvidia_cudnn_cu12-9.28.1.4-py3-none-win_amd64.whl"
)
CUDNN_BIN = TOOLS / "cudnn" / "bin"
MT_MODEL = "hunyuan-mt-7b"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[跳过] {dest.name} 已存在")
        return

    tmp = dest.with_name(dest.name + ".part")
    pos = tmp.stat().st_size if tmp.exists() else 0
    headers = {"User-Agent": "Mozilla/5.0"}
    if pos:
        headers["Range"] = f"bytes={pos}-"

    print(f"[下载] {dest.name}（已下载 {pos / 1024**3:.1f} GB）")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("ab" if pos else "wb") as f:
        if pos and resp.status != 206:
            f.seek(0)
            f.truncate()
            pos = 0
        total = int(resp.headers.get("Content-Length") or 0) + pos
        done = pos
        started = last = time.time()
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            now = time.time()
            if now - last >= 2:
                speed = (done - pos) / (now - started) / 1024**2
                pct = f"{done / total * 100:5.1f}%" if total else "  ?  "
                print(f"\r  {pct}  {done / 1024**3:5.1f} GB  {speed:5.1f} MB/s", end="")
                last = now
    print()
    tmp.replace(dest)


def install_ollama() -> None:
    target = TOOLS / "ollama"
    if (target / "ollama.exe").exists():
        OLLAMA_ZIP.unlink(missing_ok=True)
        print("[跳过] 便携 Ollama 已解压")
        return
    download(OLLAMA_URL, OLLAMA_ZIP)
    tmp = TOOLS / "_ollama_extract"
    if tmp.exists():
        shutil.rmtree(tmp)
    print("[解压] Ollama ...")
    with zipfile.ZipFile(OLLAMA_ZIP) as z:
        z.extractall(tmp)
    exe = next(tmp.rglob("ollama.exe"), None)
    if exe is None:
        raise RuntimeError("Ollama 压缩包里找不到 ollama.exe")
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(exe.parent), str(target))
    shutil.rmtree(tmp, ignore_errors=True)
    OLLAMA_ZIP.unlink(missing_ok=True)
    print(f"[完成] {target / 'ollama.exe'}")


def prepare_cudnn() -> None:
    if (CUDNN_BIN / "cudnn64_9.dll").exists():
        CUDNN_WHEEL.unlink(missing_ok=True)
        print("[跳过] cuDNN 已解压")
        return
    download(CUDNN_URL, CUDNN_WHEEL)
    print("[解压] cuDNN ...")
    CUDNN_BIN.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(CUDNN_WHEEL) as z:
        for name in z.namelist():
            if name.lower().endswith(".dll"):
                (CUDNN_BIN / Path(name).name).write_bytes(z.read(name))
    CUDNN_WHEEL.unlink(missing_ok=True)
    print(f"[完成] {CUDNN_BIN}")


def prepare_mt() -> None:
    download(GGUF_URL, GGUF)
    runtime = OllamaRuntime(PROJECT)
    try:
        runtime.start()
        if runtime.has_model(MT_MODEL):
            print("[跳过] 翻译模型已创建")
        else:
            print("[创建] Ollama 模型 hunyuan-mt-7b（需要几分钟）...")
            runtime.create_model(MT_MODEL, GGUF)
        print("[验证] 英译中 ...")
        import json

        payload = json.dumps(
            {
                "model": MT_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Translate the following segment into Chinese, "
                            "without additional explanation.\n\n"
                            "Hello, how are you?"
                        ),
                    }
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 64},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            runtime.host + "/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print("[验证结果] " + data["message"]["content"].strip())
    finally:
        runtime.close()


def prepare_asr() -> None:
    from faster_whisper.utils import download_model

    print("[下载] faster-whisper large-v3-turbo ...")
    try:
        path = download_model("large-v3-turbo")
    except Exception:
        path = download_model("deepdml/faster-whisper-large-v3-turbo-ct2")
    print(f"[完成] {path}")


def main() -> None:
    TOOLS.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    install_ollama()
    prepare_cudnn()
    prepare_mt()
    prepare_asr()
    MARKER.write_text("ok\n", encoding="utf-8")
    print("\n初始化完成。以后双击 start.bat 即可。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
