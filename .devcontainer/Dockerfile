FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Fix Yarn repository GPG key issue - remove the Yarn repo to prevent
# feature installation failures. The Yarn InRelease file is signed with key
# 62D54FD4003F6525 which is no longer in their pubkey.gpg
RUN rm -f /etc/apt/sources.list.d/yarn.list

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    openssl \
    curl \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV NODE_OPTIONS=--use-openssl-ca
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

USER vscode

# Pre-create VS Code server volume mount points owned by vscode so Docker
# initializes the named volumes with vscode:vscode ownership rather than root,
# preventing permission errors when VS Code tries to install its server on
# first container start.
RUN mkdir -p /home/vscode/.vscode-server \
    /home/vscode/.vscode-server-insiders \
    /home/vscode/.copilot

# Install UV and global Python CLI tools (each in an isolated uv-managed venv)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ~/.local/bin/uv tool install pytest && \
    ~/.local/bin/uv tool install autoflake && \
    ~/.local/bin/uv tool install flake8 && \
    ~/.local/bin/uv tool install bump2version && \
    ~/.local/bin/uv tool install build

ENV PATH="/home/vscode/.local/bin:${PATH}"
