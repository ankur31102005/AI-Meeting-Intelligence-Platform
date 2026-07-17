# =====================================================================
# Backend image — serves BOTH the API and the Celery worker (the
# command differs per docker-compose service, the image is identical).
#
# python:3.12-slim (not 3.14): the AI stack arriving in Modules 5-7
# (torch, faster-whisper, pyannote) has the widest prebuilt-wheel
# support on 3.12 — dependable > bleeding-edge for a production image.
# =====================================================================
FROM python:3.12-slim

# Sensible Python defaults for containers:
#  - no .pyc litter, unbuffered stdout (logs appear immediately)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}

# ffmpeg: audio extraction (Module 5). curl: container healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, code second — Docker layer caching means editing
# app code does NOT re-run pip install on every build.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Never run as root inside the container (defense in depth).
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default command = API server. The worker service overrides this in
# docker-compose with: celery -A app.workers.celery_app:celery_app worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
