# Build from the `services/git-settings` directory
FROM python:3.11-alpine3.18 AS builder

RUN apk add --update --no-cache git curl build-base libffi-dev

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /service
COPY pyproject.toml /service/pyproject.toml
RUN uv venv --python "$(which python)" && \
    uv pip install -r pyproject.toml

FROM python:3.11-alpine3.18
ENV PYTHONUNBUFFERED=1

# Runtime needs the real `git` binary, not just the library
RUN apk add --update --no-cache git

COPY --from=builder /service/.venv /venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /service
COPY worker /service/worker

RUN addgroup -S ayonuser && adduser -SH ayonuser -G ayonuser \
    && mkdir -p /storage/settings_git \
    && chown -R ayonuser:ayonuser /service /storage/settings_git

USER ayonuser

CMD ["python", "-m", "worker"]
