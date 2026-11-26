# Contrats inter-services – UniTrack (version 1)

> Document **à partager avec toute l'équipe** : c'est ce qui permet aux 6 services de s'assembler sans se bloquer.
> Rédigé par S4 ; S1, S2, S3, S5, S6 doivent confirmer/ajuster leurs parties (via Pull Request sur ce fichier).

## 1. Conventions communes

| Sujet | Convention |
|---|---|
| Préfixes Traefik | `/api/auth` (S1) · `/api/users` (S2) · `/api/academic` (S3) · `/api/attendance` (S4) · `/api/notifications` (S5) · `/api/statistics` (S6) |
| Identifiants | Les ids utilisateur/groupe/module/salle sont des **chaînes opaques**. `sub` du JWT = id utilisateur utilisé partout (S2, S3, S4). |
| JWT (émis par S1) | Claims obligatoires : `sub`, `exp`, `role` ∈ `ADMIN` · `SUPERVISEUR` · `ENSEIGNANT` · `ETUDIANT`. Optionnel : `email`, `iss`, `aud`. |
| Vérification JWT | Locale dans chaque service (HS256 + secret partagé hors Git, ou RS256 + clé publique de S1). |
| Erreurs HTTP | `{"error": "<code_machine>", "detail": "<message>"}` |
| Broker | RabbitMQ, exchange **topic durable** `unitrack.events`. Dead-letter : `unitrack.dlx`. |
| Enveloppe d'événement | `{"event_id","event_type","version":1,"source","occurred_at","data":{...}}` + propriété AMQP `message_id` = `event_id`. |
| Idempotence | Tout consommateur ignore un `event_id` déjà traité. |
| Versionnage | Suffixe `.v1` dans la routing key ; un changement cassant = `.v2` en parallèle. |

## 2. Événements que S3 (Academic) DOIT publier pour S4

| Routing key | `data` |
|---|---|
| `academic.seance.upserted.v1` | `{"id","module":{"id","name","semester"},"group":{"id","label"},"teacher":{"id","name"},"room":{"id","name"},"date":"AAAA-MM-JJ","start_time":"HH:MM","end_time":"HH:MM","type":"COURS\|TD\|TP"}` |
| `academic.seance.deleted.v1` | `{"id"}` |
| `academic.enrollment.upserted.v1` | `{"student_id","group_id","matricule","first_name","last_name","email"}` |
| `academic.enrollment.removed.v1` | `{"student_id","group_id"}` |

S3 publie à chaque création/modification validée (sans conflit) d'une séance et à chaque affectation étudiant→groupe.
Pour rattraper l'existant : S3 republie l'état complet (les handlers de S4 sont des *upserts* idempotents).

## 3. Événements publiés par S4

| Routing key | Déclencheur | Consommateurs prévus | `data` (extrait) |
|---|---|---|---|
| `attendance.recorded.v1` | Présence enregistrée (code ou appel manuel) | S6 | `seance_id, module_id, group_id, student_id, statut, mode, …` |
| `attendance.absence_threshold_reached.v1` | Un étudiant **atteint** 3 (orange) ou 5 (rouge) absences dans un module | **S5** (e-mail étudiant + administration), S6 | `student_id, student_email, student_name, module_id, module_intitule, absences_count, level, threshold, notify_admin` |
| `attendance.session.started.v1` | Séance démarrée | S6 | données de la séance |
| `attendance.session.closed.v1` | Séance clôturée | S6 | séance + `present_count, absent_count, absent_student_ids, closed_by` |
| `attendance.session.not_held.v1` | Enseignant déclaré absent (séance non assurée) | **S5** (alerte administration), S6 | données de la séance + `notify_admin` |

Données de séance communes : `seance_id, academic_seance_id, module_id, module_intitule, group_id, group_label, enseignant_id, enseignant_nom, salle_nom, date_seance, heure_debut, heure_fin, type_seance`.

**S5** : binder une queue sur `attendance.absence_threshold_reached.*` et `attendance.session.not_held.*`.
**S6** : binder `attendance.#` et construire son modèle de lecture (ne jamais lire `attendance_db`).

## 4. API REST de S4 (préfixe `/api/attendance/v1`) – Swagger : `/api/attendance/docs/`

| Méthode & chemin | Rôle(s) | Description |
|---|---|---|
| `GET /seances/today/` | Enseignant, Étudiant | Séances du jour |
| `GET /seances/current/` | Étudiant | Séances en cours de son groupe |
| `GET /seances/` · `GET /seances/{id}/` | Tous (filtré par rôle) | Liste filtrable (`statut, group_id, module_id, enseignant_id, date_from, date_to`) |
| `POST /seances/{id}/start/` | Enseignant | Démarre la séance, renvoie le code (6 chiffres, 5 min) |
| `GET /seances/{id}/code/` | Enseignant | Code courant + secondes restantes |
| `POST /seances/{id}/regenerate-code/` | Enseignant | Nouveau code (nouvelle fenêtre de 5 min) |
| `GET /seances/{id}/presences/` | Enseignant, Admin, Superviseur | Appel en temps réel (présents/absents/en attente) |
| `PUT /seances/{id}/presences/{student_id}/` | Enseignant | Appel manuel `{"statut":"PRESENT\|ABSENT"}` (séance en cours) |
| `POST /seances/{id}/close/` | Enseignant | Clôture : non-pointés → ABSENTS, contrôle des seuils |
| `GET /seances/{id}/export/` | Enseignant, Admin, Superviseur | CSV de la liste de présence |
| `POST /seances/{id}/check-in/` | Étudiant | Saisie du code `{"code","latitude?","longitude?"}` |
| `GET /seances/non-assurees/` | Admin, Superviseur | FP13 – séances non assurées |
| `GET /me/attendance/` | Étudiant | Assiduité par module (`module_id, date_from, date_to, details=1`) |
| `GET /me/alerts/` | Étudiant | Modules en orange/rouge |
| `GET /history/` | Admin, Superviseur | Historique filtrable (`group_id, module_id, enseignant_id, student_id, statut, date_from, date_to`) |
| `GET /dashboard/` | Enseignant, Admin, Superviseur | Tableau de bord synthétique |
| `GET/PUT /settings/` | Admin | Validité du code, seuils, géolocalisation |
| `GET /health/` *(hors préfixe)* | – | Health-check Consul |

Codes d'erreur métier : `session_not_active` (409) · `invalid_code` (400) · `code_expired` (410) · `already_recorded` (409) ·
`not_in_group` (403) · `location_required` (400) · `out_of_range` (403) · `forbidden` (403) · `too_early` (409) · `too_late` (409) · `not_today` (400) · `invalid_state` (409) · `student_not_in_group` (404).
