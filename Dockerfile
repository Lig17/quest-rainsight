FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RAINSIGHT_DATA_DIR=/app/data
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY rainsight ./rainsight
COPY web ./web
COPY data/*.json ./data/
EXPOSE 8000
CMD ["sh", "-c", "uvicorn rainsight.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
