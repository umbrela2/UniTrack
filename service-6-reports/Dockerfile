FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt gunicorn

COPY --chown=app:app . .

USER app

EXPOSE 8006

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8006", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
