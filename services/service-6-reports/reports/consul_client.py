import logging
import os

import requests

logger = logging.getLogger(__name__)

SERVICE_NAME = 's6-reports'
SERVICE_ID = 's6-reports-8006'
SERVICE_PORT = 8006
SERVICE_TAGS = [
    'traefik.enable=true',
    'traefik.http.routers.s6-reports.rule=PathPrefix(`/api/statistics`)',
    'statistics',
]
HEALTH_CHECK_URL = 'http://s6-reports:8006/health/'


def _consul_base_url():
    host = os.getenv('CONSUL_HOST', 'localhost')
    port = os.getenv('CONSUL_PORT', '8500')
    return f'http://{host}:{port}'


def register_service():
    try:
        payload = {
            'ID': os.getenv('CONSUL_SERVICE_ID', SERVICE_ID),
            'Name': os.getenv('CONSUL_SERVICE_NAME', SERVICE_NAME),
            'Address': os.getenv('CONSUL_SERVICE_ADDRESS', SERVICE_NAME),
            'Port': int(os.getenv('CONSUL_SERVICE_PORT', SERVICE_PORT)),
            'Tags': SERVICE_TAGS,
            'Check': {
                'HTTP': os.getenv(
                    'CONSUL_HEALTH_CHECK_URL',
                    HEALTH_CHECK_URL,
                ),
                'Interval': os.getenv('CONSUL_HEALTH_INTERVAL', '10s'),
                'Timeout': os.getenv('CONSUL_HEALTH_TIMEOUT', '3s'),
                'DeregisterCriticalServiceAfter': os.getenv(
                    'CONSUL_DEREGISTER_AFTER',
                    '1m',
                ),
            },
        }
        response = requests.put(
            f'{_consul_base_url()}/v1/agent/service/register',
            json=payload,
            timeout=3,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning(
            'Consul registration skipped (%s): %s',
            _consul_base_url(),
            exc,
        )
        return False

    logger.info('Service %s registered with Consul.', payload['ID'])
    return True


def deregister_service():
    service_id = os.getenv('CONSUL_SERVICE_ID', SERVICE_ID)
    try:
        response = requests.put(
            f'{_consul_base_url()}/v1/agent/service/deregister/{service_id}',
            timeout=3,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning(
            'Consul deregistration skipped (%s): %s',
            _consul_base_url(),
            exc,
        )
        return False

    logger.info('Service %s deregistered from Consul.', service_id)
    return True
