import datetime as dt
import time

import jwt
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.models import Enrollment, Seance


def make_token(sub, role, secret="test-secret", exp_delta=3600):
    return jwt.encode({"sub": sub, "role": role, "email": f"{sub}@x.dz", "exp": int(time.time()) + exp_delta},
                      secret, algorithm="HS256")


def client_for(sub, role):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(sub, role)}")
    return c


@pytest.fixture
def teacher():
    return client_for("teacher-1", "ENSEIGNANT")


@pytest.fixture
def admin():
    return client_for("admin-1", "ADMIN")


def student(i):
    return client_for(f"student-{i}", "ETUDIANT")


@pytest.fixture
def group(db):
    for i in range(1, 6):
        Enrollment.objects.create(student_id=f"student-{i}", group_id="G1", matricule=f"M{i}", nom=f"N{i}",
                                  prenom=f"P{i}", email=f"s{i}@x.dz")


def make_seance(module="M1", teacher_id="teacher-1", start_offset=-5, duration=90, group_id="G1", sid=None):
    now = timezone.localtime().replace(second=0, microsecond=0)
    start = now + dt.timedelta(minutes=start_offset)
    end = start + dt.timedelta(minutes=duration)
    if start.date() != end.date() or start.date() != now.date():        # évite les tests à minuit
        start, end = now.replace(hour=0, minute=1), now.replace(hour=23, minute=58)
    return Seance.objects.create(
        academic_seance_id=sid or f"a-{Seance.objects.count() + 1}", module_id=module, module_intitule=f"Module {module}",
        group_id=group_id, group_label="G1", enseignant_id=teacher_id, enseignant_nom="Dr X",
        date_seance=start.date(), heure_debut=start.time(), heure_fin=end.time())
