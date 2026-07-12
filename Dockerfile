# (c) 2026 jag.m.singh@gmail.com

# Pinned to the digest verified working 2026-07-12 (Debian trixie, ffmpeg 7.1.5).
# ffmpeg's I/O scheduling changed meaningfully across majors (see main.py's
# queue comment); base-image upgrades are a decision, not a rebuild side effect.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

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
