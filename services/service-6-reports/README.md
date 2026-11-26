# Service 6 — Statistiques & Rapports (UniTrack)

Microservice Django 5 / Django REST Framework du projet **UniTrack** pour
l'Université M'hamed Bougara – Boumerdès. Service **headless** (sans interface
HTML) : il expose uniquement une API REST JSON pour les statistiques
d'assiduité, les rapports exportables (Excel/PDF) et un endpoint de
synchronisation avec les autres services. Le frontend React est développé et
hébergé séparément.

| Élément | Valeur |
| --- | --- |
| Service | `s6-reports` |
| Port HTTP | `8006` |
| Base de données (Docker) | `statistics_db` (PostgreSQL 16) |
| Base locale par défaut | SQLite (`db.sqlite3`) |
| Documentation OpenAPI | `/api/docs/` |

## Fonctionnalités

- API REST JSON consommable par le frontend React (CORS ouvert).
- KPI d'assiduité, répartition des présences, taux par module et par groupe.
- Détection des étudiants en alerte / exclusion selon des seuils paramétrables.
- Liste des séances non assurées.
- Fiche statistique par étudiant (matricule).
- Exports Excel (openpyxl) et PDF (ReportLab) filtrés.
- Synchronisation idempotente des groupes, modules, salles, enseignants,
  étudiants, séances et présences.
- Enregistrement automatique dans Consul (`s6-reports`, port `8006`).
- Consommation asynchrone RabbitMQ des événements `session.*` et
  `attendance.*`.
- Authentification JWT compatible avec le service S1 Auth.
- Routage Traefik sur `/api/reports` via des labels Docker.

## Prérequis

- Python 3.11 ou supérieur (3.12 recommandé en local).
- Docker Desktop et Docker Compose v2 pour le déploiement conteneurisé.
- PostgreSQL 16 uniquement si vous n'utilisez pas Docker pour la base.
- Consul et RabbitMQ sont facultatifs en local : le service démarre même
  s'ils sont indisponibles.

## Installation locale sous Windows

```powershell
# Depuis service-6-reports
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_mock_data
python manage.py runserver 8006
```

Si l'activation du venv est bloquée par la stratégie PowerShell, appelez
directement l'interpréteur :

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver 8006
```

Accès :

- Santé du service : <http://127.0.0.1:8006/api/reports/health/>
- Documentation API : <http://127.0.0.1:8006/api/docs/>
- Schéma OpenAPI : <http://127.0.0.1:8006/api/schema/>
- Administration Django : <http://127.0.0.1:8006/admin/>

Pour utiliser PostgreSQL en local, créez une base `statistics_db`, puis dans
`.env` :

```dotenv
USE_SQLITE=False
USE_POSTGRES=True
DB_NAME=statistics_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

Puis relancez `python manage.py migrate`.

## Démarrage avec Docker

Le fichier `docker-compose.yml` démarre deux services :

- `statistics_db` : PostgreSQL 16, volume persistant `statistics_db_data` ;
- `s6-reports` : image construite depuis `Dockerfile` (Python 3.11-slim,
  Gunicorn), exposée sur le port `8006`, migrations appliquées au démarrage,
  connectée au réseau externe `unitrack_net` et routée par Traefik sur
  `/api/reports`.

Le réseau externe doit exister avant le démarrage :

```powershell
docker network create unitrack_net
docker compose up --build -d
docker compose exec s6-reports python manage.py seed_mock_data
```

Accès : <http://localhost:8006/api/reports/health/>

Commandes utiles :

```powershell
docker compose logs -f s6-reports
docker compose exec s6-reports python manage.py migrate
docker compose down
docker compose down -v   # supprime aussi le volume PostgreSQL
```

Variables d'environnement surchargeables (PowerShell) :

```powershell
$env:POSTGRES_DB = "statistics_db"
$env:POSTGRES_USER = "postgres"
$env:POSTGRES_PASSWORD = "postgres"
$env:SECRET_KEY = "une-cle-secrete"
$env:JWT_SIGNING_KEY = "cle-partagee-avec-s1-auth"
docker compose up --build -d
```

## Configuration

Le fichier `.env` est chargé automatiquement par `config/settings.py`.

| Variable | Défaut | Description |
| --- | --- | --- |
| `SECRET_KEY` | clé de développement | Clé secrète Django |
| `DEBUG` | `True` | Mode debug |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hôtes autorisés, séparés par des virgules |
| `USE_SQLITE` | `False` (`True` dans `.env.example`) | Force SQLite local même si PostgreSQL est activé |
| `USE_POSTGRES` | `False` | Active PostgreSQL au lieu de SQLite |
| `DB_NAME` | `statistics_db` | Nom de la base |
| `DB_USER` | `postgres` | Utilisateur PostgreSQL |
| `DB_PASSWORD` | `postgres` | Mot de passe PostgreSQL |
| `DB_HOST` | `localhost` | Hôte PostgreSQL (`statistics_db` sous Docker) |
| `DB_PORT` | `5432` | Port PostgreSQL |
| `CONSUL_HOST` | `localhost` | Hôte de l'agent Consul |
| `CONSUL_PORT` | `8500` | Port HTTP de Consul |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | URL AMQP du broker |
| `JWT_SIGNING_KEY` | `SECRET_KEY` | Clé de signature partagée avec S1 Auth |
| `REQUIRE_AUTH` | `False` | Exige un JWT sur les endpoints API |

Fuseau horaire : `Africa/Algiers`. Langue : `fr-fr`.

Les seuils d'alerte et d'exclusion sont stockés dans le modèle
`ParametresSeuils` (valeurs par défaut : alerte ≥ 3 absences non justifiées,
exclusion ≥ 5) et modifiables depuis l'administration Django.

### Consul

Au démarrage (hors commandes `migrate` et `test`), le service s'enregistre
auprès de Consul sous l'identifiant `s6-reports-8006` avec le nom
`s6-reports`, le port `8006`, les tags `traefik.enable=true`, `reports` et
`statistics`. Le contrôle de santé Consul appelle
`http://s6-reports:8006/api/reports/health/`. Si Consul est indisponible,
l'échec est journalisé en avertissement et Django continue de démarrer.

### RabbitMQ

Le consommateur asynchrone écoute l'exchange topic `unitrack.events` via la
file durable `s6_statistics_queue`, liée aux routings keys `session.*` et
`attendance.*`. Chaque message JSON est traité par la même logique
transactionnelle que `POST /api/reports/sync/` :

```powershell
python manage.py consume_events
```

L'URL du broker est lue depuis `RABBITMQ_URL`. Les messages invalides sont
rejetés sans être remis en file ; les erreurs sont journalisées.

### Authentification JWT

`JWTAuthentication` (djangorestframework-simplejwt) est activé avec la clé
`JWT_SIGNING_KEY`, qui doit être identique à celle du service S1 Auth. Par
défaut, `REQUIRE_AUTH=False` laisse les endpoints ouverts pour le
développement local et Swagger. L'endpoint `/health/` reste toujours public
pour les sondes Consul et Traefik.

### Traefik

Les labels du conteneur `s6-reports` activent Traefik et routent le préfixe
`/api/reports` vers le port `8006` du service sur le réseau externe
`unitrack_net`.

## API REST

Service purement headless : toutes les réponses métier sont en JSON (ou
Excel/PDF pour les exports), sans aucun rendu HTML. Toutes les routes sont
préfixées par `/api/reports/`.

`CORS_ALLOW_ALL_ORIGINS = True` est activé dans `config/settings.py` afin que
le frontend React séparé puisse appeler l'API sans blocage CORS.

| Méthode | Chemin | Description |
| --- | --- | --- |
| `GET` | `/health/` | État du service (`service`, `status`, `port`) |
| `GET` | `/dashboard/summary/` | KPI, statistiques par module/groupe, étudiants à risque, répartition des présences |
| `GET` | `/non-assured-sessions/` | Liste des séances au statut « Non assurée » |
| `GET` | `/student/<matricule>/` | Statistiques d'assiduité d'un étudiant |
| `POST` | `/sync/` | Synchronisation des données depuis les autres services |
| `GET` | `/export/excel/` | Export Excel du rapport filtré |
| `GET` | `/export/pdf/` | Export PDF du rapport filtré |
| `GET` | `/api/schema/` | Schéma OpenAPI 3 |
| `GET` | `/api/docs/` | Documentation Swagger UI |

### Filtres communs

Les endpoints `dashboard/summary/`, `non-assured-sessions/` et les exports
acceptent :

| Paramètre | Type | Description |
| --- | --- | --- |
| `groupe_id` | entier | Identifiant externe du groupe |
| `module_id` | entier | Identifiant externe du module |
| `enseignant_id` | entier | Identifiant externe de l'enseignant |
| `date_from` | date `YYYY-MM-DD` | Date minimale de la séance |
| `date_to` | date `YYYY-MM-DD` | Date maximale de la séance |

`/dashboard/summary/` accepte en plus un périmètre par rôle :

| Paramètre | Valeurs | Description |
| --- | --- | --- |
| `role` | `admin`, `superviseur`, `enseignant`, `etudiant` | Restreint les données |
| `user_id` | entier | Enseignant concerné (rôle `enseignant`) |
| `matricule` | chaîne | Étudiant concerné (rôle `etudiant`) |

### Export

`/export/excel/` et `/export/pdf/` acceptent les filtres communs ainsi que :

| Paramètre | Valeurs | Description |
| --- | --- | --- |
| `report_type` | `attendance_summary` (défaut), `students_at_risk`, `non_assured_sessions` | Contenu du rapport |

Exemple :

```text
/api/reports/export/pdf/?report_type=students_at_risk&module_id=1&date_from=2026-01-01
```

### Réponse `/dashboard/summary/`

```json
{
  "kpis": {
    "total_seances_cloturees": 45,
    "total_seances_non_assurees": 8,
    "taux_assiduite_global": 84.96,
    "total_absences_non_justifiees": 203,
    "etudiants_en_alerte_count": 5,
    "etudiants_en_exclusion_count": 2
  },
  "by_module": [
    {
      "module_id": 1,
      "module": "Algorithmique avancée",
      "nb_seances": 6,
      "taux_assiduite": 81.67,
      "total_absences": 33
    }
  ],
  "by_groupe": [],
  "students_at_risk": [],
  "presence_breakdown": {
    "presents": 1073,
    "absents": 203,
    "justifies": 74
  }
}
```

### Synchronisation

`POST /sync/` accepte un objet contenant tout ou partie des clés `groupes`,
`modules`, `salles`, `enseignants`, `etudiants`, `seances`, `presences`.
Chaque entité est identifiée par son `external_id` (les présences par le
couple séance + étudiant). L'opération est transactionnelle : toute référence
invalide annule l'ensemble de la synchronisation.

```json
{
  "groupes": [
    {"external_id": 1, "numero": 1, "annee_etude": 3, "specialite": "Génie Logiciel"}
  ],
  "presences": [
    {"seance_id": 1, "etudiant_id": 1, "statut_presence": "Présent"}
  ]
}
```

## Données de démonstration

```powershell
python manage.py seed_mock_data
```

La commande est idempotente et crée 5 groupes, 8 modules, 6 salles,
8 enseignants, 150 étudiants, 60 séances et 1 350 présences. Les matricules
`UMB20230001` et `UMB20230031` sont en exclusion, `UMB20230002`,
`UMB20230004` et `UMB20230032` en alerte.

## Tests

```powershell
python manage.py test
```

Les tests couvrent les endpoints santé, les agrégations du tableau de bord
(API JSON), les filtres et rôles, les seuils, les séances non assurées, les
statistiques étudiant, la synchronisation et les exports Excel/PDF.

## Structure

```text
service-6-reports/
├── config/                 # Settings, URLs et WSGI Django
├── reports/
│   ├── management/commands/
│   │   ├── consume_events.py
│   │   └── seed_mock_data.py
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py             # Enregistrement Consul au démarrage
│   ├── consul_client.py    # Client d'enregistrement Consul
│   ├── exporters.py        # Génération Excel et PDF
│   ├── models.py
│   ├── rabbitmq_consumer.py
│   ├── sync.py             # Logique de synchronisation
│   ├── tests.py
│   ├── urls.py
│   ├── utils.py            # Filtres, agrégations et seuils
│   └── views.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── manage.py
```
