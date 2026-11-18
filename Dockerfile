FROM python:3.12-slim

# Systembibliotheken für WeasyPrint (Pango/HarfBuzz) + DejaVu für Ornament-Zeichen
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Abhängigkeiten zuerst (besseres Layer-Caching)
COPY pyproject.toml README.md ./
RUN mkdir -p src/krimi && touch src/krimi/__init__.py && pip install --no-cache-dir . && pip uninstall -y krimidinner
# Code, Prompts, PDF-Vorlagen und Schriften (editable, damit prompts/ und templates/ gefunden werden)
COPY src ./src
COPY prompts ./prompts
COPY templates ./templates
RUN pip install --no-cache-dir --no-deps -e .

ENV KRIMI_OUTPUT_DIR=/data/output \
    KRIMI_CACHE_DIR=/data/cache \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["krimi", "serve", "--host", "0.0.0.0", "--port", "8000"]
