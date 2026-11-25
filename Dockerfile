FROM python:3.12-slim
LABEL authors="APozhar"

WORKDIR /

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
# Use a pip version that handles platform_release markers on WSL2 kernels.
RUN python -m pip install --no-cache-dir "pip>=26.2.2" \
    && python -m pip install --no-cache-dir -r requirements.txt


COPY app ./app
COPY test ./test
COPY *.py ./
COPY docker/init_test_s3.py ./docker/init_test_s3.py

# Set uvloop as default event loop policy
ENV PYTHONPATH=/app
ENV UVICORN_LOOP=uvloop
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--loop", "uvloop", "--proxy-headers"]
