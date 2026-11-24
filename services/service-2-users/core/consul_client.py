"""
Enregistrement de S2 dans Consul (API HTTP de l'agent, sans dépendance externe).

- ID unique par instance  -> plusieurs instances de S2 possibles (load balancing Traefik)
- Health check HTTP sur /health/ toutes les 10 s
- DeregisterCriticalServiceAfter : si l'instance reste en échec 1 min (service arrêté
  ou serveur tombé), Consul la retire tout seul.
"""
import json
import urllib.request

from django.conf import settings


def service_id():
    return f"{settings.SERVICE_NAME}-{settings.SERVICE_HOST}-{settings.SERVICE_PORT}"


def _agent_url(path):
    return f"http://{settings.CONSUL_HOST}:{settings.CONSUL_PORT}/v1/agent/service/{path}"


def _put(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method="PUT", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def traefik_tags():
    """Tags lus par Traefik (provider Consul Catalog) : routage dynamique."""
    name = settings.SERVICE_NAME
    rule = (
        "PathPrefix(`/api/users`) || PathPrefix(`/api/students`) "
        "|| PathPrefix(`/api/teachers`)"
    )
    return [
        "traefik.enable=true",
        f"traefik.http.routers.{name}.rule={rule}",
        f"traefik.http.routers.{name}.entrypoints=web",
    ]


def register():
    payload = {
        "ID": service_id(),
        "Name": settings.SERVICE_NAME,
        "Address": settings.SERVICE_HOST,
        "Port": settings.SERVICE_PORT,
        "Tags": ["unitrack", "users", "django"] + traefik_tags(),
        "Check": {
            "Name": "S2 health",
            "HTTP": f"http://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}/health/",
            "Method": "GET",
            "Interval": "10s",
            "Timeout": "3s",
            "DeregisterCriticalServiceAfter": "1m",
        },
    }
    return _put(_agent_url("register"), payload)


def deregister():
    return _put(_agent_url(f"deregister/{service_id()}"))
