# Guide de déploiement multi-serveurs - S2 (User Management)

Suit les 5 étapes du guide de l'énoncé WAMS, puis la sauvegarde (FC6).
Rôles des machines : **serveur infra** (Traefik + Consul + RabbitMQ) et **serveur S2** (API + consumer + users_db).
Chaque microservice de l'équipe tourne sur son propre serveur.

| Machine | Ports à ouvrir | Utilité |
|---|---|---|
| Infra | 80 (Traefik), 8500 (Consul), 5672 (AMQP) ; 8080 et 15672 réservés à l'équipe | entrée, registre, broker |
| S2 | 8002 (API, joignable par Consul/Traefik) | API S2 |
| S2 (prod) | 5433 : **à retirer** du `docker-compose.s2.yml` | la base ne doit pas être exposée |

## 1. Préparation des serveurs
Sur chaque machine : Docker + plugin Compose installés, dépôt cloné, pare-feu réglé (tableau ci-dessus).
```bash
docker --version && docker compose version
git clone <url-du-depot> && cd UniTrack/services/service-2-users
```

## 2. Démarrage du broker + registry (serveur infra)
```bash
docker compose up -d          # fichier docker-compose.yml : traefik, consul, rabbitmq
docker ps                     # 3 conteneurs "Up"
```
Vérifier : Consul `http://<IP-infra>:8500`, RabbitMQ `http://<IP-infra>:15672`, Traefik `http://<IP-infra>:8080`.
Durcissement conseillé : définir `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` (ne pas garder `guest`).

## 3. Déploiement du microservice (serveur S2)
1. Copier la **clé publique de S1** dans `keys/auth_public.pem`.
2. `cp .env.docker.example .env.docker` puis renseigner :
```
ALLOWED_HOSTS=<IP-S2>,localhost
DB_PASSWORD=<mot de passe fort>   SECRET_KEY=<chaîne aléatoire longue>   DEBUG=False
RABBITMQ_URL=amqp://<user>:<pass>@<IP-infra>:5672/
CONSUL_HOST=<IP-infra>
SERVICE_HOST=<IP-S2>
```
3. Lancer :
```bash
docker compose -f docker-compose.s2.yml --env-file .env.docker up -d --build
docker ps                      # s2-users-db, s2-api, s2-consumer
docker logs s2-api             # migrate + "Service enregistré : user-management-<IP-S2>-8002"
```
Le health check de Consul appelle `http://<IP-S2>:8002/health/` : l'IP de S2 doit figurer dans `ALLOWED_HOSTS`.

## 4. Configuration du reverse proxy
Rien à configurer à la main : S2 s'annonce à Consul avec les tags `traefik.*`
(`/api/users`, `/api/students`, `/api/teachers`) et Traefik (provider Consul Catalog) crée la route.
```bash
curl -i http://<IP-infra>/api/users/ -H "Authorization: Bearer <token>"     # 200 via Traefik
```
Dashboard Traefik (`:8080`) : le router `user-management` doit apparaître, serveur = `<IP-S2>:8002`.

## 5. Tests de la communication asynchrone
Préparer un consommateur de contrôle : RabbitMQ UI → Queues → créer `debug.user_events`
→ Bindings : exchange `unitrack.events`, routing key `user.#`.

| Scénario | Action | Résultat attendu |
|---|---|---|
| Publication | `POST /api/users/` via Traefik | message `user.created` dans `debug.user_events` |
| Import massif | `POST /api/users/import/` avec `docs/import_1000.csv` | 1000 messages `user.created` ; `GET /api/users/import/{id}/` : `done`, durée |
| Consommation | publier `group.deleted` (UI RabbitMQ, voir `docs/events.md`) | `group_id` mis à NULL + `user.updated` publié |
| Résilience | `docker stop unitrack-rabbitmq` puis `docker start` | le consumer se reconnecte seul (logs `s2-consumer`) |

## Preuves à capturer (livrable "preuve du déploiement multi-serveurs")
1. `docker ps` sur le serveur infra **et** sur le serveur S2 (avec l'IP / hostname visibles).
2. Consul : `user-management` en vert avec l'adresse `<IP-S2>:8002`.
3. Traefik : router `user-management` actif.
4. Requête via Traefik (port 80) → 200.
5. RabbitMQ : messages `user.created` ; consumer actif.
6. `pytest` : tous les tests passés ; GitHub Actions vert.

## 6. Sauvegarde et restauration (FC6)
**Serveur Linux** (cron quotidien à 02:00, conservation 7 jours) :
```bash
chmod +x deploy/backup/*.sh
./deploy/backup/backup.sh                       # test manuel → backups/users_db_AAAAMMJJ_HHMMSS.sql.gz
crontab -e   # ajouter :
0 2 * * * cd /opt/unitrack/service-2-users && ./deploy/backup/backup.sh >> backups/backup.log 2>&1
```
**Test de restauration** (sans toucher aux vraies données) :
```bash
./deploy/backup/restore.sh backups/users_db_XXXX.sql.gz users_db_restore_test
# affiche le nombre d'utilisateurs restaurés : doit égaler celui de users_db
```
**Restauration réelle** (arrêter d'abord l'API) :
```bash
docker compose -f docker-compose.s2.yml stop api consumer
./deploy/backup/restore.sh backups/users_db_XXXX.sql.gz
docker compose -f docker-compose.s2.yml start api consumer
```
**Sur Windows (démo locale, PowerShell)** :
```powershell
docker exec s2-users-db pg_dump -U postgres -d users_db --clean --if-exists --no-owner -f /tmp/users_db.sql
mkdir backups -Force; docker cp s2-users-db:/tmp/users_db.sql backups/users_db_demo.sql
# test de restauration dans une base jetable
docker exec s2-users-db createdb -U postgres users_db_restore_test
docker cp backups/users_db_demo.sql s2-users-db:/tmp/restore.sql
docker exec s2-users-db psql -U postgres -d users_db_restore_test -v ON_ERROR_STOP=1 -q -f /tmp/restore.sql
docker exec s2-users-db psql -U postgres -d users_db_restore_test -c "SELECT count(*) FROM users_user;"
```
Ajouter `backups/` au `.gitignore`.

## Dépannage rapide
| Symptôme | Cause probable |
|---|---|
| Consul rouge (400) | IP de S2 absente de `ALLOWED_HOSTS` |
| Consul rouge (refused) | port 8002 bloqué par le pare-feu / API arrêtée |
| Pas de route dans Traefik | tags non vus : `docker restart s2-api` |
| 401 sur toutes les requêtes | clé publique ≠ clé de S1, ou token expiré |
| Aucune réception des événements | queue non liée à `unitrack.events` (routing key) |
