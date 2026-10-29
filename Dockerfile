# Eligible: API, demo page and engineering notes on port 8000.
# Model calls use the Anthropic API inside the container: pass ANTHROPIC_API_KEY.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/app/.hf

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev \
 && uv run python -m eligible.retrieve.ingest   # downloads the local embedding model once

ENV ELIGIBLE_LLM_BACKEND=anthropic_api
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "eligible.api:app", "--host", "0.0.0.0", "--port", "8000"]
