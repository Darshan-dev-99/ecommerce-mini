FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_ENV=prod \
    PORT=8000

WORKDIR /app

# libpq is only needed at build time for psycopg's binary wheel discovery;
# curl powers the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 shop \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R shop:shop /app
USER shop

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=4s --start-period=25s --retries=4 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/system/health/" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "60", "--access-logfile", "-"]
