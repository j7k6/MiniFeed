FROM python:3-slim

ENV FLASK_ENV=production

COPY requirements.txt /tmp/

RUN pip install -r /tmp/requirements.txt

WORKDIR /app
CMD ["/app/minifeed.py"]
