# Truth Guardian web app in one image, also used as the Hugging Face Space (Docker SDK, port 7860).
# Building needs internet (packages, datasets with checksums, language models); the app then runs offline.
#   docker build -t truth-guardian .
#   docker run -p 7860:7860 -e TG_ACCESS_CODE=choose-a-code truth-guardian   ->  http://127.0.0.1:7860
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_NO_CACHE=1
RUN pip install uv==0.11.23 && useradd -m -u 1000 user
WORKDIR /home/user/app

# The locked packages, with the CPU build of PyTorch instead of the CUDA one (no GPU here; about 3 GB smaller).
COPY --chown=user pyproject.toml uv.lock README.md ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/locked.txt \
 && grep -v -E "^(nvidia-|cuda-|triton)" /tmp/locked.txt > /tmp/requirements.txt \
 && uv pip install --system --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt

COPY --chown=user . .
RUN uv pip install --system --no-deps -e .

USER user
ENV HOME=/home/user HF_HOME=/home/user/.cache/huggingface HF_HUB_DOWNLOAD_TIMEOUT=60
RUN python scripts/download_data.py \
 && python scripts/build_data.py \
 && python scripts/build_perturbations.py \
 && python scripts/build_tg_agent.py
RUN python scripts/export_onnx.py || echo "ONNX export failed; the app still runs, about a third slower"
# Large model files, fetched with retries (resumable); the weights only, not the other formats the repos also hold.
RUN for attempt in 1 2 3 4 5; do \
      python -c "from huggingface_hub import snapshot_download as get; skip = ['onnx/*', 'openvino/*', '*.h5', '*.msgpack', '*.ot', 'tf_*', 'flax_*', 'rust_*']; [get(m, ignore_patterns=skip) for m in ('sentence-transformers/all-MiniLM-L6-v2', 'cross-encoder/nli-deberta-v3-base')]" \
      && break || sleep 20; \
    done
RUN python -m truth_guardian.web --prepare

ENV HF_HUB_OFFLINE=1 TG_ALLOWED_HOSTS="*.hf.space"
EXPOSE 7860
CMD ["python", "-m", "truth_guardian.web", "--host", "0.0.0.0", "--port", "7860", "--no-browser"]
