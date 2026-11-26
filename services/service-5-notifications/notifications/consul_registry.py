import requests
import socket

CONSUL_HOST = "127.0.0.1"  # À remplacer par l'IP du serveur Consul le jour du déploiement
CONSUL_PORT = 8500
SERVICE_NAME = "service-5-notifications"
SERVICE_PORT = 8005

def register_service():
    local_ip = socket.gethostbyname(socket.gethostname())
    payload = {
        "ID": f"{SERVICE_NAME}-{SERVICE_PORT}",
        "Name": SERVICE_NAME,
        "Address": local_ip,
        "Port": SERVICE_PORT,
        "Check": {
            "HTTP": f"http://{local_ip}:{SERVICE_PORT}/health/",
            "Interval": "10s",
            "Timeout": "5s"
        }
    }
    try:
        res = requests.put(f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/register", json=payload, timeout=3)
        if res.status_code == 200:
            print(f"[Consul] Service {SERVICE_NAME} enregistré avec succès ({local_ip}:{SERVICE_PORT})")
    except Exception as e:
        print(f"[Consul] Consul non joignable actuellement : {e}")