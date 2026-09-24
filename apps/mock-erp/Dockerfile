FROM python:3.12-slim

WORKDIR /app

# Only the mock ERP's own manifest and source: the image carries neither API
# nor the AI stack. Build context is apps/mock-erp (see docker-compose.yml).
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "mock_erp.main:app", "--host", "0.0.0.0", "--port", "8000"]
