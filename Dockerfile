# (c) 2026 jag.m.singh@gmail.com
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Unbuffered logs; nice-to-have for `docker logs -f`
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
