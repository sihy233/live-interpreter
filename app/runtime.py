"""私有 Ollama 服务的启动与回收。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _KillOnCloseJob:
    """父进程无论如何退出，关闭句柄都会杀掉整个子进程树。"""

    def __init__(self) -> None:
        self._handle = None
        self._k32 = None
        if os.name != "nt":
            return
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        handle = k32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW 失败")
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = k32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            k32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject 失败")
        self._handle = handle
        self._k32 = k32

    def assign(self, proc: subprocess.Popen) -> None:
        if not self._handle:
            return
        self._k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._k32.AssignProcessToJobObject.restype = wintypes.BOOL
        if not self._k32.AssignProcessToJobObject(
            self._handle, wintypes.HANDLE(proc._handle)
        ):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject 失败")

    def close(self) -> None:
        if self._handle:
            self._k32.CloseHandle(self._handle)
            self._handle = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class OllamaRuntime:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.exe = self.project_dir / "tools" / "ollama" / "ollama.exe"
        self.models_dir = self.project_dir / "models" / "ollama"
        self.log_path = self.project_dir / "logs" / "ollama.log"
        self.host: str | None = None
        self.proc: subprocess.Popen | None = None
        self._job: _KillOnCloseJob | None = None
        self._log = None

    def start(self) -> str:
        if self.proc is not None and self.proc.poll() is None and self.host:
            return self.host
        if not self.exe.exists():
            raise RuntimeError(
                f"找不到 Ollama：{self.exe}\n请先运行：uv run python setup.py"
            )

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        port = _free_port()
        self.host = f"http://127.0.0.1:{port}"

        env = os.environ.copy()
        env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
        env["OLLAMA_MODELS"] = str(self.models_dir)

        self._log = self.log_path.open("ab")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            [str(self.exe), "serve"],
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        try:
            self._job = _KillOnCloseJob()
            self._job.assign(self.proc)
        except OSError as exc:
            print(f"警告：无法建立进程回收 Job，关闭窗口时可能残留 Ollama：{exc}")

        self._wait_ready(timeout=60)
        return self.host

    def _wait_ready(self, timeout: float) -> None:
        assert self.host is not None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(
                    f"Ollama 启动失败（退出码 {self.proc.returncode}），"
                    f"日志：{self.log_path}"
                )
            try:
                with urllib.request.urlopen(self.host + "/api/version", timeout=1) as r:
                    if r.status == 200:
                        return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError(f"Ollama 在 {timeout:.0f}s 内未就绪，日志：{self.log_path}")

    def _env(self) -> dict[str, str]:
        assert self.host is not None
        env = os.environ.copy()
        env["OLLAMA_HOST"] = self.host.removeprefix("http://")
        env["OLLAMA_MODELS"] = str(self.models_dir)
        return env

    def has_model(self, name: str) -> bool:
        assert self.host is not None
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            return False
        wanted = {name, f"{name}:latest"}
        return any(m.get("name") in wanted or m.get("model") in wanted for m in data.get("models", []))

    def create_model(self, name: str, gguf_path: Path) -> None:
        assert self.host is not None
        gguf_path = Path(gguf_path)
        modelfile = gguf_path.parent / f"Modelfile.{name}"
        modelfile.write_text(
            f"FROM ./{gguf_path.name}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(self.exe), "create", name, "-f", str(modelfile)],
            cwd=str(gguf_path.parent),
            env=self._env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                "创建 Ollama 模型失败：\n"
                + (result.stderr.strip() or result.stdout.strip())
            )

    def close(self) -> None:
        # 关闭 Job 句柄会杀掉整棵 Ollama 进程树，显存随之释放。
        if self._job is not None:
            self._job.close()
            self._job = None

        if self.proc is not None:
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)

        if self._log is not None:
            self._log.close()
            self._log = None
        self.proc = None
        self.host = None
