FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY apps/api ./apps/api
COPY packages ./packages

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/packages:/app/apps/api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

