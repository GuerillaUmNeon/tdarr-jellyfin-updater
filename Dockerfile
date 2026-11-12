FROM alpine:3.20

ENV TZ=Europe/Amsterdam
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache python3 tzdata

WORKDIR /app

COPY app.py /app/app.py
COPY crontab /etc/crontabs/root
COPY .env /app/.env

RUN chmod 600 /app/.env && \
    chmod 755 /app/app.py && \
    chmod 644 /etc/crontabs/root

CMD ["crond", "-f", "-d", "8"]