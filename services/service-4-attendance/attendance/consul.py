"""Enregistrement / découverte Consul. Module volontairement indépendant de Django
(appelé depuis gunicorn.conf.py avant le chargement de l'application)."""
import logging
import os
import socket

import requests

log = logging.getLogger("consul")


def _cfg():
    port = int(os.environ.get("SERVICE_PORT", os.environ.get("PORT", "8004")))
    address = os.environ.get("SERVICE_ADDRESS") or socket.gethostbyname(socket.gethostname())
    name = os.environ.get("SERVICE_NAME", "attendance-service")
    return {
        "enabled": os.environ.get("CONSUL_ENABLED", "true").lower() in ("1", "true", "yes"),
        "base": f"http://{os.environ.get('CONSUL_HOST', 'localhost')}:{os.environ.get('CONSUL_PORT', '8500')}",
        "name": name, "port": port, "address": address,
        "id": os.environ.get("SERVICE_ID") or f"{name}-{address}-{port}",
        "prefix": os.environ.get("TRAEFIK_PATH_PREFIX", "/api/attendance"),
    }


def register():
    c = _cfg()
    if not c["enabled"]:
        return False
    router = c["name"]
    payload = {
        "ID": c["id"], "Name": c["name"], "Address": c["address"], "Port": c["port"],
        # Tags lus par le provider consulCatalog de Traefik → routage + load balancing dynamiques
        "Tags": ["traefik.enable=true",
                 f"traefik.http.routers.{router}.rule=PathPrefix(`{c['prefix']}`)",
                 f"traefik.http.routers.{router}.entrypoints=web",
                 f"traefik.http.services.{router}.loadbalancer.healthcheck.path=/health/",
                 "unitrack", "S4", "v1"],
        "Meta": {"version": "1.0.0", "owner": "S4-attendance"},
        "Check": {"HTTP": f"http://{c['address']}:{c['port']}/health/", "Interval": "10s", "Timeout": "3s",
                  "DeregisterCriticalServiceAfter": "1m"},
    }
    r = requests.put(f"{c['base']}/v1/agent/service/register", json=payload, timeout=5)
    r.raise_for_status()
    log.warning("Consul : service %s enregistré (%s:%s)", c["id"], c["address"], c["port"])
    return True


def deregister():
    c = _cfg()
    if not c["enabled"]:
        return
    try:
        requests.put(f"{c['base']}/v1/agent/service/deregister/{c['id']}", timeout=5)
        log.warning("Consul : service %s retiré", c["id"])
    except requests.RequestException as exc:
        log.warning("Consul : désenregistrement impossible (%s)", exc)


def discover(service_name):
    """Retourne les instances *saines* d'un service : [{'address','port','id'}]."""
    c = _cfg()
    r = requests.get(f"{c['base']}/v1/health/service/{service_name}", params={"passing": "true"}, timeout=5)
    r.raise_for_status()
    return [{"id": e["Service"]["ID"], "address": e["Service"]["Address"] or e["Node"]["Address"],
             "port": e["Service"]["Port"]} for e in r.json()]
