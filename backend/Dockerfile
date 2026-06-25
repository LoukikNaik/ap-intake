FROM python:3.12-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install deps first (layer cache)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "openai-agents>=0.0.13" "litellm>=1.51.0" "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" "sqlalchemy>=2.0.0" "psycopg[binary]>=3.2.0" \
    "pydantic>=2.9.0" "pydantic-settings>=2.5.0" "python-multipart>=0.0.12" \
    "pymupdf>=1.24.0"

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
