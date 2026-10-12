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

# Set DATABASE_URL to keep the library in Postgres. Without it the library is a SQLite
# file here, which needs a persistent disk mounted to survive redeploys.
ENV DATA_DIR=/data
VOLUME /data
EXPOSE 8000
# One worker: the rate limiter is per-process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
