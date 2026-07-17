FROM python:3.12-slim

WORKDIR /clera

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# SQLite database + single-instance lock live here; mount it to persist.
VOLUME /clera/data

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
