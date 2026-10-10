FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /frontend/dist /app/frontend/dist

# Mount a persistent disk here so the library survives redeploys.
ENV DATA_DIR=/data
VOLUME /data
EXPOSE 8000
# One worker: the rate limiter and SQLite file are per-process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
