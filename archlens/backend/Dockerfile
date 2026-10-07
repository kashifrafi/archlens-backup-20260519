FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app ./app

# Optional samples directory (mounted by main.py if present at ../samples)
# Build context is the backend dir, so samples live one level up. We copy them
# into the image at /samples and expose via SAMPLES_DIR env override is not used,
# so we mount them at the path main.py expects: ../samples relative to /app/app
# That resolves to /samples — create a symlink so StaticFiles can find them.
RUN mkdir -p /samples
# Note: samples are copied separately at build time via build context override,
# OR baked in via the root Dockerfile. For now, /samples may be empty.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
