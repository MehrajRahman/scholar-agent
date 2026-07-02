# Orchestrator image — the LangGraph + FastAPI "Hands" container.
# Slim CPU image: the heavy GPU work lives in the vLLM/Ollama Brain containers/VMs.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Force Playwright to install browsers inside /app so the non-root user can own them
    PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

WORKDIR /app

# System deps: trafilatura/lxml need libxml2; fastembed pulls onnxruntime wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN pip install -r requirements.txt

# --- CRITICAL FIX FOR CRAWL4AI ---
# Install the headless Chromium browser and its required OS dependencies.
# This ensures JS-heavy university lab pages render correctly before extraction.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* COPY src ./src
COPY web ./web
RUN pip install -e .

# Non-root setup: Ensure the runner user owns the app directory AND the browser cache
RUN useradd -m runner && \
    mkdir -p /app/.cache && \
    chown -R runner:runner /app
USER runner

EXPOSE 8080
CMD ["uvicorn", "scholar.api.main:app", "--host", "0.0.0.0", "--port", "8080"]