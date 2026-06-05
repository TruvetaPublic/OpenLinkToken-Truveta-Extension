FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        openssl \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/detect_zscaler.sh /usr/local/bin/detect_zscaler.sh
RUN chmod +x /usr/local/bin/detect_zscaler.sh && /usr/local/bin/detect_zscaler.sh || true

RUN pip install --no-cache-dir \
        pytest \
        autoflake \
        flake8 \
        bump2version \
        build
