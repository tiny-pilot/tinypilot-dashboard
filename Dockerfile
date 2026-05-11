FROM python:3.12-slim

LABEL org.opencontainers.image.title="TinyPilot Dashboard"
LABEL org.opencontainers.image.description="Local-first multi-device dashboard for TinyPilot targets"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "run.py"]
