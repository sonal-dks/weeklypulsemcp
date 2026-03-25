FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/mcp_bridge
ENV PYTHONPATH=/app
ENV PORT=8080

CMD exec uvicorn mcp_bridge.main:app --host 0.0.0.0 --port "${PORT}"
