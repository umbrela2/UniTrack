import os
import time

bind = f"0.0.0.0:{os.environ.get('PORT', '8004')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
timeout = 30
accesslog = "-"


def when_ready(server):
    """Enregistre cette instance dans Consul (avec retries : Consul peut démarrer après nous)."""
    from attendance import consul
    for attempt in range(1, 11):
        try:
            consul.register()
            return
        except Exception as exc:  # noqa: BLE001
            server.log.warning("Consul indisponible (%s) tentative %d/10", exc, attempt)
            time.sleep(3)


def on_exit(server):
    from attendance import consul
    consul.deregister()
