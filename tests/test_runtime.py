import os
import subprocess

import pytest

from app.runtime import _KillOnCloseJob


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_job_kills_child_on_close():
    proc = subprocess.Popen(
        ["cmd", "/c", "ping", "-n", "60", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    job = _KillOnCloseJob()
    try:
        job.assign(proc)
    except OSError as exc:
        proc.kill()
        job.close()
        pytest.skip(f"当前环境不允许加入 Job Object：{exc}")
    job.close()
    proc.wait(timeout=5)
    assert proc.poll() is not None
