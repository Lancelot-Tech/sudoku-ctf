FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/            ./app/
COPY templates/      ./templates/
COPY static/         ./static/
COPY generate_puzzles.py .
COPY .env            .

# Pré-génère les puzzles au build — FLAG lu depuis .env via python-dotenv
RUN python generate_puzzles.py

RUN useradd -m -u 1000 ctfuser
USER ctfuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "warning", \
     "--timeout-keep-alive", "30"]
