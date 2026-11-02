"""Put the web app on a Hugging Face Space (Docker) so the judges can open it from a link.

Run it yourself after `hf auth login` with a token that can write to the Space. It creates the Space if needed,
uploads only what the image needs (Dockerfile, package, scripts, final models, result files) with deploy/space/README.md
as the Space card, and can set the access code as a Space secret. The Space then builds the image (packages,
datasets, models; about half an hour) and serves the app.

A public Space shows its files, including the built front end with the purchased layers, and lets anyone pull the
built image: check those licences first (docs/CREDITS.md). --private keeps it to your account and organisation.
"""

import argparse
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock",
    "src/**", "scripts/**", "models/fusion/**", "models/tracer/**", "models/profiles/**", "eval/results/**",
    "models/detector/full/*.json", "models/detector/full/model.safetensors",
]
NEVER = ["**/__pycache__/**", "**/*.pyc"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True, help="owner/name, e.g. my-team/truth-guardian")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--access-code", help="visitors must enter this code (stored as the Space secret TG_ACCESS_CODE)")
    args = parser.parse_args()

    api = HfApi()
    url = api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
    if args.access_code:
        api.add_space_secret(args.space, "TG_ACCESS_CODE", args.access_code, description="code visitors enter to open the app")
    api.upload_folder(
        repo_id=args.space, repo_type="space", folder_path=ROOT, allow_patterns=FILES, ignore_patterns=NEVER,
        commit_message="Truth Guardian web app",
    )
    api.upload_file(
        repo_id=args.space, repo_type="space", path_or_fileobj=ROOT / "deploy" / "space" / "README.md", path_in_repo="README.md",
        commit_message="Space card",
    )
    host = args.space.replace("/", "-").replace("_", "-").replace(".", "-").lower()
    print(f"uploaded to {url}; once the build finishes the app is at https://{host}.hf.space")


if __name__ == "__main__":
    main()
