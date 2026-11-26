import os
import socket

from django.db import connection
from django.http import JsonResponse


def health(request):
    checks = {}
    ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False
    if request.GET.get("deep") == "1":          # le broker n'est PAS dans le health-check Consul par défaut
        try:
            import pika
            from django.conf import settings
            pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL)).close()
            checks["rabbitmq"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["rabbitmq"] = f"error: {exc.__class__.__name__}"
            ok = False
    body = {"status": "ok" if ok else "degraded", "service": "attendance-service",
            "instance": os.environ.get("SERVICE_ID") or socket.gethostname(), "checks": checks}
    return JsonResponse(body, status=200 if ok else 503)
