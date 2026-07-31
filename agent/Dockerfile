ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.14.5-slim-trixie@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97

FROM ${PYTHON_IMAGE} AS build

ENV VIRTUAL_ENV=/opt/kinlin-venv \
    PATH=/opt/kinlin-venv/bin:$PATH

WORKDIR /build

RUN python -m venv "$VIRTUAL_ENV"
COPY agent/requirements.lock ./requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes --only-binary=:all: -r requirements.lock
COPY agent/requirements.tools.lock ./requirements.tools.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes --only-binary=:all: -r requirements.tools.lock \
    && python -m pip uninstall --yes pip

FROM ${PYTHON_IMAGE}

ARG KINLIN_VERSION=dev
ARG KINLIN_REVISION=unknown
ARG KINLIN_CREATED=unknown
LABEL org.opencontainers.image.title="Kinlin AI Service" \
      org.opencontainers.image.version="$KINLIN_VERSION" \
      org.opencontainers.image.revision="$KINLIN_REVISION" \
      org.opencontainers.image.created="$KINLIN_CREATED"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/agentOS/src:/app \
    AGENTOS_PACKS_DIR=/app/packs \
    VIRTUAL_ENV=/opt/kinlin-venv \
    PATH=/opt/kinlin-venv/bin:$PATH

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes pip \
    && ln -s "$(command -v gosu)" /usr/local/bin/su-exec \
    && groupadd --gid 10002 kinlin \
    && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin kinlin

COPY --from=build /opt/kinlin-venv /opt/kinlin-venv
COPY agent/requirements.lock ./requirements.lock
COPY agent/requirements.tools.lock ./requirements.tools.lock

COPY agent/app ./app
COPY agent/packs ./packs
COPY agent/knowledge ./knowledge
COPY agent/agentos.py ./agentos.py
COPY agentOS/src ./agentOS/src
COPY backend/src ./workspace/backend/src
COPY frontend/src ./workspace/frontend/src
COPY agent/app ./workspace/agent/app
COPY agent/packs ./workspace/agent/packs
COPY agentOS/src ./workspace/agentOS/src

RUN mkdir -p /app/data /app/logs /app/.cache /run/kinlin-secrets \
    && chown -R 10002:10002 /app /run/kinlin-secrets

COPY agent/docker-entrypoint.sh /usr/local/bin/kinlin-entrypoint
RUN chmod 0755 /usr/local/bin/kinlin-entrypoint

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/kinlin-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
