import os
import subprocess
import sys
from pathlib import Path

from truth_guardian.web.engine import ROOT

SHOW_CACHE = "import truth_guardian; from huggingface_hub import constants; print(constants.HF_HUB_CACHE)"


def hub_cache(env: dict) -> Path:
    out = subprocess.run([sys.executable, "-c", SHOW_CACHE], env=env, capture_output=True, text=True, timeout=120, check=True)
    return Path(out.stdout.strip())


def test_models_stay_in_the_project_when_hf_home_is_not_set():
    env = {k: v for k, v in os.environ.items() if k not in ("HF_HOME", "HF_HUB_CACHE")}
    assert hub_cache(env) == ROOT / "runtime" / "hf" / "hub"


def test_an_hf_home_that_is_set_is_respected(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "HF_HUB_CACHE"}
    assert hub_cache({**env, "HF_HOME": str(tmp_path)}) == tmp_path / "hub"
