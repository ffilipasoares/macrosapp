FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN useradd --system app
USER app

# Cloud Run sets PORT.
CMD ["sh", "-c", "exec uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-8080}"]
