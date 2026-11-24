FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Windows -> Linux : retire les fins de ligne CRLF du script, utilisateur non-root
RUN sed -i 's/\r$//' deploy/entrypoint.sh \
    && chmod +x deploy/entrypoint.sh \
    && mkdir -p /app/media \
    && useradd -m appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 8002
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "user_service.wsgi:application", "--bind", "0.0.0.0:8002", "--workers", "3"]
