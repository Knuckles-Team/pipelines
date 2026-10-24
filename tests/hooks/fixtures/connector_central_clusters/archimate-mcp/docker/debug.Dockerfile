# Required: pass a trusted image digest with --build-arg MCP_RUN_PYTHON_IMAGE=...@sha256:...
ARG MCP_RUN_PYTHON_IMAGE
FROM ${MCP_RUN_PYTHON_IMAGE}
USER 10001:10001
