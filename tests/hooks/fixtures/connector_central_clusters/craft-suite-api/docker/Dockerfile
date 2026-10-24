# syntax=docker/dockerfile:1
# MCP serving image. It installs the published wheel from PyPI, never the
# source tree, and builds no tools from source.
#
# The pin below tracks the package version through .bumpversion.cfg.
#
#   docker build --file docker/Dockerfile --target mcp -t craft-suite-api:<version>-mcp .
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS mcp
ARG HOST=127.0.0.1
ARG PORT=8000
ARG TRANSPORT="stdio"
ARG AUTH_TYPE="none"
ENV HOST=${HOST} \
    PORT=${PORT} \
    TRANSPORT=${TRANSPORT} \
    AUTH_TYPE=${AUTH_TYPE} \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    XDG_CONFIG_HOME=/tmp/.config \
    XDG_CACHE_HOME=/tmp/.cache
RUN pip install --only-binary :all: craft-suite-api[mcp]==0.3.3 \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --no-create-home \
        --home-dir /tmp --shell /usr/sbin/nologin app
USER 10001:10001
CMD ["craft-suite-mcp"]

FROM mcp AS default
