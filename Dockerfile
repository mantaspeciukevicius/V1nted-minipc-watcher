FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY app/ /app/
COPY tests/ /tests/
USER 1000:1000
CMD ["python", "monitor.py", "daemon"]
