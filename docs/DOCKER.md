# Truth Guardian in Docker

One Linux image runs the whole web app on the CPU, offline, with no Python, uv or packages installed on the host. It is
built for any host that runs Linux containers (Docker Engine on Linux, Docker Desktop on Windows with WSL 2 or on
macOS), but only the setups listed under [Tested](#tested) have been run; the others are expected to work, not
verified. The image is `linux/amd64` and CPU only, and it holds the current app, which checks text: photo and audio
inputs are not implemented yet.

On Windows without Docker, `TruthGuardian.bat` is the other way to run the app (see the README); the two can run side
by side, the launcher on port 8765 and the container on 7860.

## Requirements

- **Docker Engine 24.0 or later with Docker Compose v2**, or Docker Desktop with Linux containers (on Windows: the
  WSL 2 backend). Tested on Engine 24.0.9 with Compose 2.29.1 and on Engine 29.9.2 with Compose 5.6.1. The build
  uses BuildKit cache mounts (BuildKit is the default builder from Engine 23.0). The health check leaves out
  `start_interval` on purpose: it needs Engine 25.0 and Compose 2.20.2.
- **Memory: at least 2 GB for the container.** Measured: 1.4 GB once the models are loaded; with a 1 GB limit the
  container is killed while loading (exit code 137, `OOMKilled=true`). Docker Desktop gives Linux containers half the
  computer's memory by default, which is enough on an 8 GB computer.
- **Disk:** the image holds 3.3 GB of layers; Docker Desktop reports about 5.1 GB because it keeps a packed and an
  unpacked copy. The build cache adds several GB more (`docker builder prune` frees it).
- **Internet: for the build only.** Running the image never needs the network (tested with `--network none`).

| Step | Internet | What happens |
|---|---|---|
| `docker compose build` | yes, once | packages (from `uv.lock`, CPU PyTorch), datasets (checksums verified), the two language models at pinned revisions, the HHEM ONNX export, the example cache |
| `docker compose up` | no | starts the app from what is in the image; nothing is downloaded |

## Quick start

From the project folder:

```bash
docker compose up -d --build
```

Then open http://127.0.0.1:7860. The models load in the background: the page works at once, and checks start when
`docker compose ps` shows the container as `healthy` (about 17 seconds on the project laptop, longer on slower CPUs;
the check runs every 10 seconds, so `healthy` follows `ready` within 10 seconds).

## Everyday commands

| Task | Command |
|---|---|
| build (or rebuild after a code change) | `docker compose build` |
| start in the background | `docker compose up -d` |
| is it ready? | `docker compose ps` (`healthy` = ready) or http://127.0.0.1:7860/api/health (`"state": "ready"`) |
| logs | `docker compose logs -f` |
| stop, keep the container | `docker compose stop` (the status then reads `Exited (143)`, the normal stop signal) |
| stop and remove the container, **keep** the example cache | `docker compose down` |
| also delete the example cache | `docker compose down -v` |
| another host port | `TG_PORT=8000 docker compose up -d` (PowerShell: `$env:TG_PORT=8000; docker compose up -d`) |
| ask visitors for a code | `TG_ACCESS_CODE=your-code docker compose up -d`; any user name, the code as password |
| let the Contact page send mail | `TG_SMTP_USER=you@gmail.com TG_SMTP_PASSWORD=app-password docker compose up -d` (the image never contains `smtp.local.env`); the container then needs internet access to send |

`/api/health` answers from the first second, also while the models are loading. The container's health check
(`scripts/docker_healthcheck.py`, standard library only) reads its JSON and reports healthy only on `"state": "ready"`;
it never loads a model. A container whose models failed to load shows `"state": "failed"` with the reason, answers
checks with HTTP 503 and the same reason, and turns `unhealthy` after the five-minute start period.

Stopping waits for a check that is running: stopped four seconds into an 18-second analysis, the container finished
it, answered and exited after 9.4 seconds. Docker allows 30 seconds (`stop_grace_period`) before it kills the app.

## What is stored where

- **In the image (read only):** the code, the built front end, the locked packages, the trained models, the HHEM ONNX
  export, the two language models, WordNet, the model card results and the four development files the app shows
  examples from. Not in the image: raw datasets, training data and the locked test sets (they exist only in an
  intermediate build stage).
- **Named volume `truth-guardian_web-cache`:** the example cache in `data/web`, the only place the app writes. It is
  filled from the image on first start and survives `restart`, `down` and rebuilds; a new model or code version
  simply recomputes its reports. Back it up with
  `docker run --rm -v truth-guardian_web-cache:/v -v "$PWD":/b alpine tar czf /b/web-cache.tgz -C /v .`
- **Nothing else.** Documents and answers sent to the app are processed in memory and not saved; the root file system
  is read only (`/tmp` is an in-memory tmpfs).

## Security

- The port is published on **127.0.0.1 only**, so nothing outside this computer reaches the app. Inside the
  container the app listens on all interfaces (it has to); it prints a warning when no `TG_ACCESS_CODE` is set.
- The app runs as a non-root user (uid 1000) on a read-only root file system. No secret is built into the image;
  `TG_ACCESS_CODE` is given at run time only and never logged.
- Host names other than localhost are refused (HTTP 400) unless listed in `TG_ALLOWED_HOSTS` (the image allows
  `*.hf.space` for the Hugging Face Space).
- Telemetry is off: Hugging Face (`HF_HUB_DISABLE_TELEMETRY`) and ONNX Runtime (`ORT_DISABLE_TELEMETRY`).
- Before exposing it beyond this computer: put it behind a TLS proxy, set `TG_ALLOWED_HOSTS` to your host name and
  use a strong `TG_ACCESS_CODE`. There is no default code in the repository.

## Pinned versions

| Part | Version |
|---|---|
| base image | `python:3.13.17-slim-trixie@sha256:d98cc29d…` |
| uv | `ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39…` |
| Python packages | `uv.lock` (exported with `--frozen`); PyTorch 2.14.1+cpu from the PyTorch CPU index |
| sentence encoder | `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243` (safetensors only, 92 MB) |
| NLI model | `cross-encoder/nli-deberta-v3-base` @ `6c749ce3` (safetensors only, 749 MB) |
| HHEM | `vectara/hallucination_evaluation_model` @ `de9a5e6b`, exported to ONNX at build time and checked against PyTorch |

The revisions live in `src/truth_guardian/models.py` (`REVISIONS`) and are used by the app, the readiness check and
the build alike. Packages are installed without hashes because the CPU PyTorch wheels differ from the ones the lock
records; their versions are the locked ones. Licences: `docs/CREDITS.md` (also in the image).

## GPU

The image is CPU only and needs no GPU. Asking for one on a computer without an NVIDIA GPU fails before the app starts
(`docker run --gpus all …` gives `nvidia-container-cli: … no adapters were found`), so leave `--gpus` out. A GPU
variant (Linux with the NVIDIA Container Toolkit, or Windows with WSL 2 and an NVIDIA driver; never macOS) is future
work: it would be a separate build target with the CUDA build of PyTorch, offered only once tested on such a machine.

## Tested

| | |
|---|---|
| date | 2026-10-27 |
| host | Windows 11 Pro 10.0.26300, AMD Ryzen 7 5800H (16 threads), 16 GB RAM, AMD integrated graphics (no NVIDIA) |
| Docker | Docker Desktop 4.97.0, Engine 29.9.2, Compose 5.6.1, Buildx 0.38.1, WSL 2.6.1 (kernel 6.6.87.2) |
| oldest Docker | Engine 24.0.9, Compose 2.29.1, Buildx 0.16.2, run as Docker-in-Docker (`docker:24-dind`) on the same host |
| image | `linux/amd64`, 3.3 GB of layers |

| Check | Result |
|---|---|
| `docker compose config` | valid, no unset variables |
| build | from an empty build cache 6.0 min (downloads included); after a code change 2.6 min; a failed model download or export stops the build with a message, and a final offline readiness check fails the build if anything is missing |
| cold start | `starting` → app `warming` (5 s) → `ready` (16 s) → `healthy` (17 s); never healthy before ready |
| Engine 24.0.9 (Docker-in-Docker) | `compose config` valid; build from an empty cache 4.6 min; `healthy` in 21 s; page, health, cached example and fresh analysis as above; ready in 13 s with `--network none` |
| page, health, a cached example, a fresh analysis | 200; example from the cache in 0.01 s; a wrong year flagged in 0.5 s (risk 0.91) |
| no network (`--network none`, read-only root) | ready in 14 s, every probe as above |
| restart; `down` then `up` | ready in 17 s; the example cache kept (19 reports) |
| access code | without or with a wrong code 401, with the code 200, health 200; the code never in the logs |
| foreign host name | 400 `Invalid host header` |
| host port in use | compose stops with `ports are not available … 127.0.0.1:7870` |
| language models missing | readiness check lists them as MISS (exit 1); the app reports `failed` with the reason and answers 503 |
| memory | 1 GB limit: killed while loading (137, OOMKilled); 2 GB: ready, an 18-second analysis completes, 1.3 GB used |
| stop during an analysis | the analysis finishes and is answered; stopped after 9.4 s |
| GPU requested, none present | Docker refuses with a clear error; inside the image `torch.cuda.is_available()` is False and the app runs on the CPU |

To repeat the main checks (from the project folder; Docker Desktop or the Docker engine must be running):

```bash
docker compose config --quiet                     # the compose file is valid
docker compose up -d --build && docker compose ps # healthy once the models are ready
docker run --rm --network none --read-only --tmpfs /tmp truth-guardian:local python -m truth_guardian.web --check
docker run --rm --entrypoint ls truth-guardian:local data/processed   # only the four development files
docker compose down
```

The oldest Docker check runs Engine 24 inside a privileged container, so the project is built from an empty cache there
(about 5 minutes, internet needed), then removed with its data:

```bash
docker run -d --privileged --name tg-dind24 -e DOCKER_TLS_CERTDIR= -v "$PWD:/src:ro" docker:24-dind
docker exec tg-dind24 sh -c "cd /src && docker compose build && docker compose up -d"
docker exec tg-dind24 docker compose -f /src/compose.yaml ps    # healthy after about 20 seconds
docker rm -f -v tg-dind24
```

**Not tested, so not claimed:** Linux on its own hardware (only the WSL 2 Linux kernel of Docker Desktop), macOS
(Intel or Apple Silicon), `linux/arm64` (would need a native ARM64 run, not just an emulated build), any GPU, and
the image photo input, which the app does not have yet.
