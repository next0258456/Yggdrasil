FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY vault ./vault
COPY evals ./evals

RUN uv pip install --system --no-cache .

EXPOSE 8300

CMD ["sh", "-c", "if [ ! -f /app/data/gold_sales_obt.parquet ]; then python /app/data/seed_data.py; fi && uvicorn y7l_tools.api:app --host 0.0.0.0 --port ${Y7L_TOOLS_PORT:-8300}"]
