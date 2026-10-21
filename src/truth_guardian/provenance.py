import subprocess
from pathlib import Path


def git_commit(root: Path) -> str:
    """HEAD, marked dirty only when code or dependencies differ from it (result files do not count)."""
    run = lambda *cmd: subprocess.run(["git", *cmd], cwd=root, capture_output=True, text=True).stdout.strip()
    dirty = run("status", "--porcelain", "--", "src", "scripts", "pyproject.toml", "uv.lock")
    return run("rev-parse", "--short", "HEAD") + ("-dirty" if dirty else "")
