# Contrat des événements RabbitMQ - S2 (User Management)

Version du contrat : 1 - à valider avec S1 (Auth), S3 (Academic), S4 (Attendance), S5 (Notifications), S6 (Statistics).

## Transport
- **Exchange** : `unitrack.events` (type `topic`, durable)
- **Routing key** = type de l'événement (ex. `user.created`)
- Chaque service consommateur déclare **sa propre queue** et la lie à l'exchange
  (ex. `auth.user_events` liée à `user.*`).
- Messages persistants, JSON, `content_type = application/json`.

## Enveloppe commune
```json
{
  "event_id": "b3f1c7e2-....",
  "event_type": "user.created",
  "version": 1,
  "source": "user-management",
  "occurred_at": "2026-11-21T13:14:01.494179+00:00",
  "data": { }
}
```
`event_id` : identifiant unique. Livraison **au moins une fois** : les consommateurs
doivent être **idempotents** (ignorer un `event_id` déjà traité).

## Événements publiés par S2
| Routing key | Déclencheur | Consommateurs prévus |
|---|---|---|
| `user.created` | POST /api/users/ ou import CSV/Excel | S1 (crée les identifiants + mot de passe temporaire), S5 (e-mail de bienvenue), S6 |
| `user.updated` | PUT/PATCH profil, PATCH /me/ | S4 (changement de groupe), S5 (langue), S6 |
| `user.activated` | PATCH /{id}/activate/ ou POST /{id}/restore/ | S1 (réactive la connexion) |
| `user.deactivated` | PATCH /{id}/deactivate/ | S1 (bloque la connexion), S4 |
| `user.deleted` | DELETE /{id}/ (soft delete) | S1 (supprime/bloque les identifiants), S4, S6 |

**Remarque suppression** : `user.deleted` correspond à une suppression *logique* (le compte
reste en base dans S2, même `user_id`). S1 doit donc **bloquer** la connexion sans effacer
définitivement les identifiants : un compte restauré renvoie `user.activated`.

## Payload `data` (identique pour les 5 événements)
```json
{
  "user_id": "uuid",
  "email": "sara@univ-boumerdes.dz",
  "first_name": "Sara",
  "last_name": "Test",
  "role": "student",
  "status": "active",
  "language": "fr",
  "department_id": null,
  "student": { "matricule": "20240001", "group_id": "uuid|null", "section_id": "uuid|null" },
  "teacher": { "grade": "MCB" }
}
```
- `student` n'est présent que pour `role = student`, `teacher` que pour `role = teacher`.
- Données minimales (loi 18-07) : pas de téléphone, pas de date de naissance.
- `user_id` est l'identifiant partagé avec S1 : c'est le claim `sub` du JWT.

## Événements consommés par S2
Queue : `users.group_events` (durable), liée à l'exchange `unitrack.events`.
Process séparé : `python manage.py consume_events`.

| Routing key | Émetteur | Action dans S2 |
|---|---|---|
| `group.deleted` | S3 | `group_id` mis à NULL pour les étudiants du groupe, puis `user.updated` publié pour chacun |

Format attendu de `group.deleted` (à confirmer avec S3) :
```json
{ "event_id": "uuid", "event_type": "group.deleted", "data": { "group_id": "uuid" } }
```
Traitement idempotent. En cas d'erreur : un nouvel essai, puis le message est écarté (journalisé).

## Limite connue
La publication se fait après le commit de la base. Si RabbitMQ est indisponible, l'utilisateur
est créé mais l'événement est perdu (erreur journalisée). Amélioration possible : pattern
*Outbox* (table d'événements en attente rejouée par un worker).
