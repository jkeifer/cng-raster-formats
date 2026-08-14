# The jupyter/docker-stacks images have no Python 3.14 build yet, so we assemble
# our own: uv installs and manages the interpreter, and a multi-stage build drops
# the resulting venv onto a clean Debian base.

# ---- builder: uv-managed CPython + resolved venv ---------------------------
FROM ghcr.io/astral-sh/uv:trixie-slim AS builder

# Both the interpreter and the venv that references it get copied into the
# runtime stage, so they must live at fixed paths that are identical in both.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN uv python install 3.14

WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# ---- runtime ---------------------------------------------------------------
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash jovyan

COPY --from=builder /opt/python /opt/python
COPY --from=builder /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH

USER jovyan

# compose bind-mounts the repo here; if this and the mount point disagree,
# JupyterLab silently serves an empty directory.
WORKDIR /home/jovyan

EXPOSE 8888

# tini reaps the kernel processes JupyterLab spawns.
ENTRYPOINT ["tini", "-g", "--"]
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--no-browser", "--IdentityProvider.token="]
