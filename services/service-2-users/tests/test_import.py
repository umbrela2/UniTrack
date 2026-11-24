import time
import types
from datetime import date

import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from imports.models import ImportJob
from imports.tasks import process_import
from users.models import User

pytestmark = pytest.mark.django_db

EXAMPLE = (
    "email,first_name,last_name,role,matricule,date_of_birth,place_of_birth,grade\n"
    "amine.test@univ-boumerdes.dz,Amine,Benali,student,20240101,2004-03-12,Alger,\n"
    "lina.test@univ-boumerdes.dz,Lina,Merabet,student,20240102,2003-11-30,Boumerdès,\n"
    "karim.test@univ-boumerdes.dz,Karim,Saidi,teacher,,,,MCA\n"
    "sans.matricule@univ-boumerdes.dz,Nour,Haddad,student,,,,\n"
).encode("utf-8")


@pytest.fixture
def run_import(settings, tmp_path, monkeypatch):
    """Exécute process_import de façon synchrone sur un fichier en mémoire."""
    settings.MEDIA_ROOT = tmp_path
    # process_import ferme la connexion à la fin (thread) : on neutralise pour les tests
    monkeypatch.setattr("imports.tasks.connection", types.SimpleNamespace(close=lambda: None))

    def _run(content, name="users.csv"):
        job = ImportJob.objects.create(file=SimpleUploadedFile(name, content), filename=name)
        process_import(job.id)
        job.refresh_from_db()
        return job

    return _run


# ------------------------------------------------------------------ traitement
def test_example_file(run_import):
    job = run_import(EXAMPLE)
    assert job.status == "done"
    assert (job.total, job.success_count, job.error_count) == (4, 3, 1)
    assert job.errors[0]["line"] == 5
    assert "student_profile" in job.errors[0]["errors"]
    assert User.objects.count() == 3


def test_reimport_rejects_existing_accounts(run_import):
    run_import(EXAMPLE)
    job = run_import(EXAMPLE)
    assert job.success_count == 0
    assert job.error_count == 4


def test_missing_columns_make_the_job_fail(run_import):
    job = run_import(b"email,first_name\na@test.dz,A\n")
    assert job.status == "failed"
    assert "Colonnes manquantes" in str(job.errors)


def test_semicolon_separator(run_import):
    content = (
        "email;first_name;last_name;role;matricule\n"
        "x1@test.dz;A;B;student;S1\n"
        "x2@test.dz;C;D;student;S2\n"
    ).encode("utf-8")
    job = run_import(content)
    assert job.success_count == 2


def test_xlsx_file(run_import, tmp_path):
    frame = pd.DataFrame([{
        "email": "x@test.dz", "first_name": "A", "last_name": "B",
        "role": "student", "matricule": "X1", "date_of_birth": "2003-05-14",
    }])
    path = tmp_path / "source.xlsx"
    frame.to_excel(path, index=False)
    job = run_import(path.read_bytes(), name="users.xlsx")
    assert job.success_count == 1, job.errors
    assert User.objects.get(email="x@test.dz").student_profile.date_of_birth == date(2003, 5, 14)


def test_invalid_role_row(run_import):
    job = run_import(b"email,first_name,last_name,role\na@test.dz,A,B,admin\n")
    assert job.error_count == 1
    assert "role" in job.errors[0]["errors"]


def test_deleted_email_error_mentions_restore(run_import, make_user):
    make_user("student", email="old@test.dz").soft_delete()
    job = run_import(
        b"email,first_name,last_name,role,matricule\nold@test.dz,A,B,student,Z1\n"
    )
    assert "supprimé" in str(job.errors)


# ------------------------------------------------------------------ endpoints
def test_upload_endpoint_returns_202(as_admin, settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr("imports.views.start_import", lambda job_id: None)
    upload = SimpleUploadedFile("users.csv", EXAMPLE, content_type="text/csv")
    response = as_admin.post("/api/users/import/", {"file": upload}, format="multipart")
    assert response.status_code == 202, response.data
    assert response.data["status"] == "pending"
    assert ImportJob.objects.count() == 1


def test_upload_rejects_wrong_extension(as_admin, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    upload = SimpleUploadedFile("users.txt", b"x")
    response = as_admin.post("/api/users/import/", {"file": upload}, format="multipart")
    assert response.status_code == 400


def test_only_admin_can_import(as_supervisor, as_student):
    upload = SimpleUploadedFile("users.csv", EXAMPLE)
    assert as_supervisor.post("/api/users/import/", {"file": upload}, format="multipart").status_code == 403
    upload = SimpleUploadedFile("users.csv", EXAMPLE)
    assert as_student.post("/api/users/import/", {"file": upload}, format="multipart").status_code == 403


def test_job_detail_endpoint(as_admin, run_import):
    job = run_import(EXAMPLE)
    response = as_admin.get(f"/api/users/import/{job.id}/")
    assert response.status_code == 200
    assert response.data["success_count"] == 3
    assert response.data["duration_seconds"] is not None


# ------------------------------------------------------------------ performance (FP2)
@pytest.mark.slow
def test_import_1000_accounts(run_import):
    lines = ["email,first_name,last_name,role,matricule"]
    for i in range(1, 1001):
        lines.append(f"etu{i:04d}@univ-boumerdes.dz,Prenom{i},Nom{i},student,2026{i:05d}")
    started = time.perf_counter()
    job = run_import("\n".join(lines).encode("utf-8"))
    elapsed = time.perf_counter() - started
    print(f"\n>>> Import de 1000 comptes (hors RabbitMQ) : {elapsed:.1f} s")
    assert job.success_count == 1000, job.errors[:3]
    assert elapsed < 120  # cahier technique : 1000 comptes en moins de 2 minutes
