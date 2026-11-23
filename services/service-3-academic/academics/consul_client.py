import logging
import os
import requests

log = logging.getLogger(__name__)


def register_in_consul():
    if os.getenv("CONSUL_ENABLED", "true").lower() != "true":
        return

    consul_host = os.getenv("CONSUL_HOST", "127.0.0.1")
    consul_port = int(os.getenv("CONSUL_PORT", "8500"))

    service_id = os.getenv("SERVICE_ID", "service-3-academic-8003")
    service_name = os.getenv("SERVICE_NAME", "service-3-academic")
    service_address = os.getenv("SERVICE_HOST", "127.0.0.1")
    service_port = int(os.getenv("SERVICE_PORT", "8003"))

    url = f"http://{consul_host}:{consul_port}/v1/agent/service/register"
    payload = {
        "ID": service_id,
        "Name": service_name,
        "Address": service_address,
        "Port": service_port,
        "Tags": [
            "unitrack",
            "academic",
            "traefik.enable=true",
            "traefik.http.routers.academic.rule=PathPrefix(`/api/academic`) || PathPrefix(`/api`)",
            f"traefik.http.services.academic.loadbalancer.server.port={service_port}",
        ],
        "Check": {
            "HTTP": f"http://{service_address}:{service_port}/health/",
            "Interval": "10s",
            "Timeout": "3s",
            "DeregisterCriticalServiceAfter": "1m",
        },
    }

    try:
        resp = requests.put(url, json=payload, timeout=3)
        resp.raise_for_status()
        log.info("Service enregistre dans Consul (%s -> %s:%s)", service_name, service_address, service_port)
    except requests.RequestException as exc:
        log.warning("Consul indisponible lors de l'enregistrement: %s", exc)
