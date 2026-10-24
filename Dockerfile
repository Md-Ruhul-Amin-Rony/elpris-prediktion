# Serves api/main.py (component C). Not used by the learn/ pipeline scripts
# themselves -- those run via GitHub Actions, not this container. Matches
# the local dev Python version (.python-version: 3.12).

FROM python:3.12-slim

# uv's own published binary, copied in rather than pip-installed -- the
# recommended way to get uv into a container without an extra install step.
COPY --from=ghcr.io/astral-sh/uv:0.9.6 /uv /uvx /usr/local/bin/

WORKDIR /app

# Reproducible, deterministic installs from the lockfile already committed
# and tested against -- not a fresh dependency resolution at build time.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Dependencies first, in their own layer: this step is cached and only
# re-runs when pyproject.toml/uv.lock change, not on every code edit.
# --no-install-project: installs dependencies only, not the project
# itself, since the source it would need isn't copied in yet.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra api --no-install-project

# Only what api/main.py actually imports at runtime -- not model/ (the
# champion comes from Hugging Face Hub at request time, never from a local
# file), not learn/db/*.sql (one-off migrations, applied by hand), not
# tests/ or docs/.
COPY api/ api/
COPY learn/ learn/

RUN uv sync --frozen --no-dev --extra api

# Least privilege: the process doesn't need root to serve HTTP.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:${PATH}"

# Render and Cloud Run both inject PORT and expect the container to listen
# on it; 8000 is just the local-run default. JSON-array CMD wrapping
# `sh -c` gets both things a bare shell-form CMD can't have together:
# $PORT still gets expanded (sh -c does that), and `exec` replaces the
# shell with uvicorn instead of running it as a child -- so uvicorn
# becomes PID 1 and actually receives SIGTERM directly for a clean
# shutdown, rather than the shell swallowing it.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port $PORT"]
