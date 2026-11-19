"""Restart only the acceptance API. Does not load a developer env file."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run  # noqa: E402

proc = subprocess.Popen(
    ["node", str(run.NODE_PYTHON), "--env=acceptance", "-m", "app.serve"],
    cwd=run.ROOT,
    env=run.child_env(),
)
(Path(__file__).resolve().parent / "api.pid").write_text(str(proc.pid), encoding="utf-8")
print("api_pid", proc.pid, flush=True)
proc.wait()
