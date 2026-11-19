# Container image for the packet builder. Runs as a Container Apps job.
# The command is set per job (for example the intake poller or the packet job),
# so one image serves both.
FROM python:3.13-slim

# Tesseract is the local OCR engine used for scanned or image-only pages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pinned dependencies first so this layer is reused when only code changes.
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY pyproject.toml .
COPY src ./src
RUN python -m pip install --no-deps . \
    && python -m pip check

RUN useradd --create-home --uid 10001 app
USER app

# In Azure, set AZURE_CLIENT_ID to the managed identity's client ID;
# DefaultAzureCredential then signs in without keys or secrets.
ENTRYPOINT ["bd-packet"]
CMD ["--help"]
