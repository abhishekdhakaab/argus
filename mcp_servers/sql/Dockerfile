FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY mcp_servers/sql/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY mcp_servers/sql /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
