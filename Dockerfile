FROM node:20-slim AS web-build

WORKDIR /app/web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TH_DATA_DIR=/data \
    TH_PORT=8000 \
    TH_WEB_DIST=/app/web/dist

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY trackhealth ./trackhealth

RUN pip install --no-cache-dir .

COPY --from=web-build /app/web/dist ./web/dist

EXPOSE 8000

CMD ["sh", "-c", "uvicorn trackhealth.api.app:app --host 0.0.0.0 --port ${TH_PORT:-8000}"]
