# S4 – Attendance Management (UniTrack / WAMS)

Microservice Django REST Framework : génération/validation des codes de présence, présences/absences, appel manuel,
clôture de séance, séances non assurées, alertes de seuil (événements RabbitMQ), enregistrement Consul, derrière Traefik.

Démarrage rapide (sans Docker) :

```bash
python -m venv .venv && source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
export USE_SQLITE=1 CONSUL_ENABLED=false                  # Windows PowerShell : $env:USE_SQLITE="1"; $env:CONSUL_ENABLED="false"
python manage.py migrate && python manage.py seed_demo
python manage.py runserver 8004                           # Swagger : http://localhost:8004/api/attendance/docs/
pytest
```

Documentation complète : `../../GUIDE_S4_COMPLET.md` · Contrats API/événements : `../../docs/CONTRATS_API_EVENEMENTS.md`
