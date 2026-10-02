# Sparr backend — uv-managed Python (PLAN.md §11)
FROM ghcr.io/astral-sh/uv:python3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000
CMD ["uv", "run", "gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
