FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# install psycopg2 dependencies.
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


RUN uv run manage.py collectstatic --noinput

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# CMD ["uv", "run", "gunicorn", "--bind", ":8000", "--workers", "2", "account.wsgi"]
CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "account.wsgi"]
