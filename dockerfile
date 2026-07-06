FROM python:3.14-slim

# Install uv directly from Astral
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# Optimize: Prevent uv from creating internal venvs inside the container system layer
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml .
COPY uv.lock .

RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

# Run migrations and then start the server
# Using sh -c allows us to chain the commands safely
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]