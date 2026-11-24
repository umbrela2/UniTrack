# UniTrack - S2 : User Management

Microservice de gestion des **profils utilisateurs** (étudiants, enseignants, administrateurs, superviseurs)
du projet UniTrack (WAMS 2026, UMBB). Port **8002**, base PostgreSQL isolée **`users_db`**.

> S2 ne gère **ni mot de passe ni connexion** : l'authentification (émission des JWT, mots de passe,
> sessions) appartient à **S1 (Auth)**. S2 vérifie seulement la signature des tokens reçus.

## Rôle dans l'architecture

```
Front (HTML/Bootstrap) ──► Traefik :80 ──► S2 API :8002 ──► users_db (PostgreSQL)
                              │                 │
                              ▼                 ▼
                         Consul :8500     RabbitMQ :5672
                    (registre + health)   user.* (publie)   group.deleted (consomme)
```

| Interaction | Mécanisme |
|---|---|
| Authentification des requêtes | JWT RS256 émis par S1, vérifié localement (clé publique) |
| Création de compte → S1 (identifiants), S5 (e-mail), S4/S6 | Événement RabbitMQ `user.created` |
| Suppression d'un groupe (S3) → mise à jour des étudiants | Consommation de `group.deleted` |
| Découverte / routage | Enregistrement Consul + tags Traefik |

Contrat détaillé des événements : [`docs/events.md`](docs/events.md).

## Stack
Python 3.12, Django + Django REST Framework, drf-spectacular (Swagger), PostgreSQL 16, RabbitMQ (pika),
Consul, Traefik, pandas/openpyxl (import), gunicorn, Docker, pytest.

## Structure
```
service-2-users/
├── user_service/     configuration Django (settings, urls)
├── core/             JWT, permissions, messaging (publisher/consumer), Consul, commandes manage.py
├── users/            modèles User / StudentProfile / TeacherProfile, API, handlers d'événements
├── imports/          import CSV/Excel asynchrone (ImportJob)
├── tests/            pytest (≈48 tests)
├── deploy/           entrypoint Docker, config Traefik, scripts de sauvegarde, guide de déploiement
├── docs/             events.md, exemples CSV
├── scripts/          dev_token.py (JWT de test), gen_import_csv.py
├── Dockerfile  docker-compose.yml (infra)  docker-compose.s2.yml (S2)
└── manage.py
```

## Installation locale (développement)
```bash
python -m venv env
env\Scripts\activate            # Linux/Mac : source env/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # puis adapter les valeurs (voir tableau plus bas)
```
1. Créer la base : `CREATE DATABASE users_db;` (PostgreSQL local).
2. `python manage.py migrate`
3. Clés JWT de test (jusqu'à réception de la clé publique de S1) :
   `python scripts/dev_token.py admin` → génère `keys/` et affiche un token.
4. `python manage.py runserver 8002`  (Swagger : http://localhost:8002/api/docs/)
5. Dans un 2e terminal, le consumer : `python manage.py consume_events`

Infra de dev (RabbitMQ + Consul + Traefik) : `docker compose up -d`.

## Variables d'environnement
| Variable | Rôle | Exemple |
|---|---|---|
| `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS` | Django | `False`, chaîne aléatoire, `localhost,10.0.0.12` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL | `users_db`, `postgres`, ..., `localhost`, `5432` |
| `JWT_PUBLIC_KEY_PATH` | Clé publique de S1 | `keys/auth_public.pem` |
| `JWT_ALGORITHM` | Algorithme | `RS256` |
| `RABBITMQ_URL`, `RABBITMQ_EXCHANGE` | Broker | `amqp://guest:guest@localhost:5672/`, `unitrack.events` |
| `CONSUL_HOST`, `CONSUL_PORT` | Registre | `localhost`, `8500` |
| `SERVICE_NAME`, `SERVICE_HOST`, `SERVICE_PORT` | Annonce dans Consul | `user-management`, IP du serveur S2, `8002` |
| `CORS_ALLOWED_ORIGINS` | Origines du front | `http://localhost:3000` |
| `RUN_MIGRATIONS`, `CONSUL_REGISTER` | Docker uniquement (entrypoint) | `True` / `False` |

Les secrets ne sont **jamais** versionnés (`.env`, `.env.docker`, `keys/` dans `.gitignore`).

## API
Documentation interactive : `/api/docs/` (Swagger) - schéma OpenAPI : `/api/schema/`
(export Postman : `python manage.py spectacular --file docs/openapi.yml`).

| Méthode | URL | Accès | Description |
|---|---|---|---|
| GET, POST | `/api/users/` | admin (superviseur : GET) | Liste (`?role=`, `?status=`, `?q=`) / création |
| GET, PUT, PATCH, DELETE | `/api/users/{id}/` | admin (superviseur : GET) | Détail, modification, suppression logique |
| PATCH | `/api/users/{id}/activate/` · `/deactivate/` | admin | Activer / désactiver |
| POST | `/api/users/{id}/restore/` | admin | Restaurer un compte supprimé |
| GET | `/api/users/?deleted=true` | admin, superviseur | Comptes supprimés |
| GET, PATCH | `/api/users/me/` | tout utilisateur authentifié | Mon profil (seuls `language` et `phone` modifiables) |
| GET | `/api/students/` · `/api/teachers/` | admin, superviseur | Listes filtrées par rôle |
| POST | `/api/users/import/` | admin | Import CSV/Excel (traitement en arrière-plan, 202) |
| GET | `/api/users/import/{id}/` | admin | Statut, compteurs, durée, rapport d'erreurs |
| GET | `/health/` | public | Health check (Consul) |

Règles d'accès (RG13, RG14) : seul l'**admin** crée/modifie ; le **superviseur** est en lecture seule ;
**enseignant** et **étudiant** n'accèdent qu'à leur propre profil via `/me/`.

### Format d'import
Colonnes obligatoires : `email, first_name, last_name, role` (`student` ou `teacher`).
Étudiant : `matricule` obligatoire ; optionnels `group_id, section_id, date_of_birth (AAAA-MM-JJ), place_of_birth`.
Enseignant : `grade` optionnel. Séparateur `,` ou `;`. Exemple : [`docs/import_example.csv`](docs/import_example.csv).
Les lignes en erreur sont listées (numéro de ligne + raison) sans bloquer les lignes valides.

## Tests
```bash
pytest -q                    # suite complète (PostgreSQL local requis, RabbitMQ simulé)
pytest -s -m slow            # import de 1000 comptes (durée affichée)
```
L'intégration continue (GitHub Actions) exécute la suite à chaque push.

## Déploiement (Docker)
```bash
docker compose up -d                                                         # Traefik + Consul + RabbitMQ
docker compose -f docker-compose.s2.yml --env-file .env.docker up -d --build # users_db + API + consumer
```
Guide complet multi-serveurs : [`deploy/README-deploy.md`](deploy/README-deploy.md).
Sauvegarde quotidienne et restauration : mêmes guide, scripts dans `deploy/backup/`.

## Choix de conception
- **UUID partagés** : l'`id` d'un utilisateur est le claim `sub` du JWT et la clé des événements.
- **Pas de clé étrangère inter-services** : `group_id`, `section_id`, `department_id` sont de simples UUID
  (propriété de S3) ; aucun service ne lit la base d'un autre.
- **Suppression logique** (`deleted_at`) : l'historique de présence (S4) reste cohérent ; un compte supprimé
  se **restaure** (même `id`) au lieu d'être recréé.
- **Données minimales dans les événements** (pas de téléphone ni date de naissance) - loi 18-07.

## Limites connues
- Publication RabbitMQ après commit : si le broker est indisponible, l'événement est perdu (journalisé).
  Amélioration : pattern *Outbox*.
- L'import tourne dans un thread du processus API ; en production : worker dédié.
- Consul en mode `-dev` et RabbitMQ `guest` : acceptables pour la démonstration, à durcir ensuite.
- HTTPS non encore activé sur Traefik.
