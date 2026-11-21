"""
Import CSV/Excel en tâche de fond (thread).
Colonnes obligatoires : email, first_name, last_name, role (student | teacher)
Colonnes optionnelles : language, phone, matricule (étudiant, obligatoire),
                        group_id, section_id, date_of_birth (AAAA-MM-JJ),
                        place_of_birth, grade (enseignant)
Chaque ligne passe par UserSerializer : mêmes validations que POST /api/users/.
"""
import logging
import threading

import pandas as pd
from django.db import connection
from django.utils import timezone

from users.serializers import UserSerializer

from .models import ImportJob

logger = logging.getLogger(__name__)

REQUIRED = ["email", "first_name", "last_name", "role"]
ALLOWED_ROLES = {"student", "teacher"}
PROGRESS_EVERY = 50


def start_import(job_id):
    threading.Thread(target=process_import, args=(job_id,), daemon=True).start()


def _plain(e):
    if isinstance(e, dict):
        return {k: _plain(v) for k, v in e.items()}
    if isinstance(e, (list, tuple)):
        return [_plain(v) for v in e]
    return str(e)


def _read(job):
    path = job.file.path
    if path.lower().endswith(".csv"):
        # sep=None : détecte "," ou ";" (exports Excel français)
        df = pd.read_csv(
            path, dtype=str, keep_default_na=False,
            encoding="utf-8-sig", sep=None, engine="python",
        )
    else:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.apply(lambda col: col.map(lambda v: str(v).strip()))
    return df[(df != "").any(axis=1)]  # ignore les lignes vides (index conservé)


def _to_payload(row):
    role = row["role"].lower()
    data = {
        "email": row["email"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "role": role,
    }
    if row.get("language"):
        data["language"] = row["language"].lower()
    if row.get("phone"):
        data["phone"] = row["phone"]
    if role == "student":
        profile = {"matricule": row.get("matricule", "")}
        for key in ("group_id", "section_id", "place_of_birth"):
            if row.get(key):
                profile[key] = row[key]
        if row.get("date_of_birth"):
            profile["date_of_birth"] = row["date_of_birth"][:10]  # "2003-05-14 00:00:00" -> date
        data["student_profile"] = profile
    else:
        data["teacher_profile"] = {"grade": row.get("grade", "")}
    return data


def process_import(job_id):
    job = ImportJob.objects.get(pk=job_id)
    job.status = ImportJob.Status.RUNNING
    job.save(update_fields=["status"])
    errors, ok = [], 0
    try:
        df = _read(job)
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"Colonnes manquantes : {', '.join(missing)}")
        job.total = len(df)
        job.save(update_fields=["total"])

        for n, (idx, row) in enumerate(df.iterrows(), start=1):
            line = idx + 2  # ligne 1 = en-têtes
            row = row.to_dict()
            if row["role"].lower() not in ALLOWED_ROLES:
                errors.append({"line": line, "email": row["email"],
                               "errors": {"role": ["Rôle invalide (student ou teacher)."]}})
            else:
                serializer = UserSerializer(data=_to_payload(row))
                if serializer.is_valid():
                    try:
                        serializer.save()
                        ok += 1
                    except Exception as exc:  # erreur inattendue sur une ligne
                        errors.append({"line": line, "email": row["email"],
                                       "errors": {"detail": [str(exc)]}})
                else:
                    errors.append({"line": line, "email": row["email"],
                                   "errors": _plain(serializer.errors)})
            if n % PROGRESS_EVERY == 0:
                job.success_count, job.error_count = ok, len(errors)
                job.save(update_fields=["success_count", "error_count"])
        job.status = ImportJob.Status.DONE
    except Exception as exc:
        logger.exception("Import %s échoué", job_id)
        job.status = ImportJob.Status.FAILED
        errors.append({"line": None, "email": "", "errors": {"detail": [str(exc)]}})
    finally:
        job.success_count, job.error_count = ok, len(errors)
        job.errors = errors
        job.finished_at = timezone.now()
        job.save()
        connection.close()  # ferme la connexion ouverte par ce thread