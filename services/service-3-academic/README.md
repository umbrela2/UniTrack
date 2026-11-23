# Service 3 — Academic & Timetable (UniTrack)

Structure académique, emplois du temps et détection de conflits.
Port **8003** · base **academic_db** (PostgreSQL 16) · Django + DRF.

## Installation
```bash
cd services/service-3-academic
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d                                  # PostgreSQL 16 (ou utiliser votre propre PG)
cp .env.example .env                                  # puis adapter
python manage.py migrate
python manage.py runserver 8003
```

## Tests
```bash
python manage.py test academics
```
(Les tests exigent PostgreSQL : l'utilisateur de la BD doit pouvoir créer une base de test
et l'extension `btree_gist`.)

## Endpoints
| Méthode | Chemin | Rôle | Description |
|---|---|---|---|
| GET/POST/PUT/PATCH/DELETE | `/api/departements/ /groupes/ /modules/ /salles/` | lecture : tous · écriture : admin | CRUD structure (UC-ADMIN-03) |
| GET/POST | `/api/seances/` | admin, enseignant | liste / création (conflits vérifiés) |
| GET/PATCH/DELETE | `/api/seances/{id}/` | admin, enseignant (les siennes) | RG6 |
| GET | `/api/seances/today/` | admin, enseignant | séances du jour (pour Service 4) |
| GET | `/api/seances/non-assurees/` | admin, superviseur | FP13, filtres `from,to,groupe,module,enseignant_id` |
| POST | `/api/timetable/check-conflicts/` | admin, enseignant | dry-run |
| GET | `/api/timetable/week/?date=&groupe=&enseignant_id=` | admin, enseignant | grille hebdo (dimanche→samedi) |

Conflit ⇒ **HTTP 409** :
```json
{"detail": "Conflit de planification : ...",
 "conflits": [{"type": "SALLE", "description": "La salle ...", "seance_id": 3}]}
```

## Garantie anti-conflit (FP3)
1. `conflicts.py` : contrôle applicatif (type + description).
2. `constraints.py` : 3 `ExclusionConstraint` PostgreSQL (enseignant / salle / groupe),
   intervalle `[début, fin)` — deux séances adjacentes (fin 10:00 / début 10:00) sont autorisées.

## Séances non assurées (FP12)
```
* * * * * cd /chemin/service-3-academic && venv/bin/python manage.py declare_absences
```
Passe en `NON_ASSUREE` les séances `PLANIFIEE` dont l'heure de fin est dépassée et envoie
l'évènement `seance.non_assuree` au Service 5 (`NOTIFICATION_URL`).

## Authentification
JWT du Service 1 (`Authorization: Bearer ...`), secret partagé `JWT_SECRET`.
Claims attendus : `user_id`, `role` (`admin`, `enseignant`, `etudiant`, `superviseur`)
— configurables dans `.env`. `AUTH_DEV_MODE=True` accepte `X-User-Id` / `X-User-Role`
(Postman/tests uniquement, **jamais en production**).

## Points à valider avec l'équipe
- Format exact du JWT (noms des claims et des rôles) avec le Service 1.
- Qui passe la séance en `EN_COURS` / `CLOTUREE` : le Service 4 doit appeler
  `PATCH /api/seances/{id}/` avec un compte admin/service, ou prévoir un endpoint dédié.
- Contradiction du CDC : « séances planifiées uniquement par l'administration »
  (périmètre exclu) vs FP4/RG6 (l'enseignant saisit son EDT). Le code autorise les deux.

## Infrastructure WAMS ajoutée (Consul, RabbitMQ, Traefik, OpenAPI)
- **Health check** : `GET /health/` (HTTP 200)
- **Consul** : auto-enregistrement au démarrage via `academics/consul_client.py`
- **RabbitMQ** : publication asynchrone des événements (`seance.non_assuree`, `timetable.conflict`) via `pika` sur l'exchange `unitrack.events`
- **Traefik** : configuration prête dans `traefik/dynamic.yml` (`PathPrefix(/api/academic)` et `PathPrefix(/api)`)
- **Documentation OpenAPI / Swagger** : `GET /api/docs/` et `GET /api/schema/` (`drf-spectacular`)
