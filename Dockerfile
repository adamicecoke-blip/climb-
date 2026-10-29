# ClipForge web app for hosting online (Render, Railway, Fly.io, a VPS...).
#   docker build -t clipforge . && docker run -p 8000:8000 -e CLIPFORGE_PASSWORD=pick-one clipforge
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the speech-to-text model at build time so the first job doesn't wait for it.
ARG WHISPER_MODEL=small
ENV CLIPFORGE_WHISPER=${WHISPER_MODEL}
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"

COPY clipforge ./clipforge
ENV CLIPFORGE_HOME=/data PORT=8000
RUN mkdir -p /data/backgrounds
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn clipforge.server:app --host 0.0.0.0 --port ${PORT}"]
