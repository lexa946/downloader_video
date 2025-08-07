FROM python:3.12-slim
LABEL authors="APozhar"

RUN apt update -y && apt install ffmpeg -y

COPY requirements.txt requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt


COPY app ./app
COPY test ./test
COPY *.py ./


CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]