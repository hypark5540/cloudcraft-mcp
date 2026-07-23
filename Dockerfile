ARG PYTHON_IMAGE=python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable \
    && .venv/bin/cloudcraft-mcp --version

FROM ${PYTHON_IMAGE} AS runtime

ARG VERSION=0.1.6
ARG REVISION=unknown

LABEL org.opencontainers.image.title="Cloudcraft MCP" \
      org.opencontainers.image.description="Unofficial stdio MCP server for Cloudcraft architecture blueprints" \
      org.opencontainers.image.source="https://github.com/hypark5540/cloudcraft-mcp" \
      org.opencontainers.image.url="https://github.com/hypark5540/cloudcraft-mcp" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="MIT" \
      io.modelcontextprotocol.server.name="io.github.hypark5540/cloudcraft-mcp"

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=build --chown=65532:65532 /app/.venv /app/.venv
COPY --chown=65532:65532 LICENSE ./LICENSE

USER 65532:65532

ENTRYPOINT ["cloudcraft-mcp"]
