# syntax=docker/dockerfile:1

# ── Base image ────────────────────────────────────────────────────────────────
# rapidsai/base ships with cuDF, RMM, and conda pre-configured.
# Adjust the tag to match your CUDA version and desired RAPIDS release.
# Tag list: https://hub.docker.com/r/rapidsai/base/tags
ARG RAPIDS_IMAGE=rapidsai/base:26.06a-cuda13-py3.13-amd64
FROM ${RAPIDS_IMAGE}

SHELL ["/bin/bash", "-c"]
USER root
WORKDIR /app

# ── cuOpt routing library ─────────────────────────────────────────────────────
# Installs cuopt (routing solver) from NVIDIA's conda channel.
# Pin the version if you need reproducible builds: cuopt=25.02.*
RUN mamba install -y -c rapidsai -c nvidia -c conda-forge cuopt \
    && mamba clean -a -y

# ── Python API dependencies ───────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
