# Smart OMR Evaluator API -- for Render (or any Docker host).
#
# Builds from the repo root, because the API imports backend_mcq_final as a
# library rather than copying it (see api/app/omr_engine.py): both api/ and
# backend_mcq_final/ have to be in the image, sitting next to each other,
# exactly as they do in this repo.
#
# PaddleOCR is deliberately NOT installed here. It needs real RAM headroom
# that Render's free tier does not have; candidate details (roll no, name)
# are entered manually instead when OCR is unavailable, which the app
# already supports (see api/app/ocr.py -- it degrades to empty fields plus a
# note, never a crash). Set ENABLE_OCR=1 and add paddleocr/paddlepaddle to
# api/requirements.txt yourself on a host with enough memory for it.

FROM python:3.11-slim

# libgl1 + libglib2.0-0: OpenCV's runtime needs these even in "headless"
# mode, or `import cv2` fails with "libGL.so.1: cannot open shared object".
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY backend_mcq_final ./backend_mcq_final
COPY api ./api

WORKDIR /app/api

ENV ENABLE_OCR=0
ENV STORAGE_BACKEND=db
# Render sets $PORT; uvicorn must bind to it, not a hardcoded port.
ENV PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
