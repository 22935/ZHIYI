FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/agentOS/src \
    AGENTOS_PACKS_DIR=/app/packs

WORKDIR /app

COPY agent/requirements_minimal.txt ./requirements_minimal.txt
RUN pip install --no-cache-dir -r requirements_minimal.txt

COPY agent/app ./app
COPY agent/packs ./packs
COPY agent/knowledge ./knowledge
COPY agent/agentos.py ./agentos.py
COPY agentOS/src ./agentOS/src

RUN mkdir -p /app/data /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
