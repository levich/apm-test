# syntax=docker/dockerfile:1.7
FROM python:3.13.15-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b AS app
COPY --from=ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/apm
COPY pyproject.toml uv.lock LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
RUN groupadd --gid 10001 apm && useradd --uid 10001 --gid apm --no-create-home apm \
    && apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/apm/.venv/bin:$PATH APM_DATA_DIR=/data PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8181
ENTRYPOINT ["apm"]
CMD ["serve"]
