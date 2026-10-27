# syntax=docker/dockerfile:1
# Truth Guardian web app in one Linux image (CPU only), also used as the Hugging Face Space (Docker SDK, port 7860).
# Building needs internet once (packages, datasets with checksums, language models at pinned revisions); the image
# then runs offline. Everyday use goes through compose.yaml; docs/DOCKER.md lists every command.
#   docker compose up -d --build   ->  http://127.0.0.1:7860

ARG PYTHON_IMAGE=python:3.13.17-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff

FROM ${UV_IMAGE} AS uv

# 1. The locked packages in /opt/venv, with the CPU build of PyTorch instead of the CUDA one (about 3 GB smaller).
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,id=tg-uv,target=/root/.cache/uv \
    uv venv /opt/venv --python /usr/local/bin/python \
 && uv export --frozen --no-dev --no-group media --no-emit-project --no-hashes -o /tmp/locked.txt \
 && grep -v -E "^(nvidia-|cuda-|triton)" /tmp/locked.txt > /tmp/requirements.txt \
 && uv pip install --python /opt/venv/bin/python --index-strategy unsafe-best-match \
      --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt

# 2. Datasets, the HHEM ONNX export, the two live language models and the example cache, built and checked here.
FROM build AS prepare
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/app/src PYTHONUNBUFFERED=1 HF_HUB_DOWNLOAD_TIMEOUT=60 HF_HUB_DISABLE_TELEMETRY=1
COPY . .
RUN python scripts/download_data.py \
 && python scripts/build_data.py \
 && python scripts/build_perturbations.py \
 && python scripts/build_tg_agent.py
# Hub downloads go through a build cache (no token is used); the image keeps only the two live models, as plain files.
RUN --mount=type=cache,id=tg-hf,target=/cache/hf \
    export HF_HOME=/cache/hf \
 && python scripts/fetch_models.py /opt/hf \
 && { python scripts/export_onnx.py \
      || { echo "ERROR: the HHEM ONNX export failed (messages above); check the internet connection and build again" >&2; exit 1; }; }
# Offline from here on, with only what the runtime image gets: the build fails if anything required is missing.
ENV HF_HOME=/opt/hf HF_HUB_OFFLINE=1
RUN python -m truth_guardian.web --prepare && python -m truth_guardian.web --check

# 3. The runtime image: the app, its packages and models, and only the development data it shows (no raw datasets,
#    no training data, no locked test sets). Runs as a non-root user; the example cache in data/web is the only
#    place it writes (a named volume in compose.yaml).
FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --create-home --uid 1000 user
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/home/user/app/src PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/user HF_HOME=/opt/hf HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 ORT_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 TRANSFORMERS_VERBOSITY=error TOKENIZERS_PARALLELISM=false \
    TG_ALLOWED_HOSTS="*.hf.space"
COPY --from=build /opt/venv /opt/venv
COPY --from=prepare /opt/hf /opt/hf
WORKDIR /home/user/app
COPY --from=prepare /app/src src
COPY --from=prepare /app/models models
COPY --from=prepare /app/eval/results eval/results
COPY --from=prepare /app/docs/CREDITS.md docs/CREDITS.md
COPY --from=prepare /app/scripts/docker_healthcheck.py scripts/docker_healthcheck.py
COPY --from=prepare /app/data/raw/nltk_data/corpora/wordnet data/raw/nltk_data/corpora/wordnet
COPY --from=prepare /app/data/processed/ragtruth_dev.jsonl /app/data/processed/xdev_halueval_dialogue.jsonl \
     /app/data/processed/tg_agent_dev.jsonl /app/data/processed/perturb_dev.jsonl data/processed/
COPY --from=prepare --chown=user /app/data/web data/web
USER user
EXPOSE 7860
HEALTHCHECK --interval=10s --timeout=5s --start-period=5m --retries=3 \
  CMD ["python", "scripts/docker_healthcheck.py"]
CMD ["python", "-m", "truth_guardian.web", "--host", "0.0.0.0", "--port", "7860", "--no-browser"]
