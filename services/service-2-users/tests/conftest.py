import datetime as dt
import itertools
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from rest_framework.test import APIClient

import core.jwt_verification as jwt_verification
from users.models import StudentProfile, TeacherProfile, User

_counter = itertools.count(1)


# ------------------------------------------------------------------ JWT de test
@pytest.fixture(scope="session")
def rsa_keys(tmp_path_factory):
    """Paire RSA jetable : la clé publique remplace celle de S1 pendant les tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_path = tmp_path_factory.mktemp("keys") / "auth_public.pem"
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": private_pem, "public_path": public_path}


@pytest.fixture(autouse=True)
def jwt_settings(settings, rsa_keys):
    settings.JWT_PUBLIC_KEY_PATH = rsa_keys["public_path"]
    jwt_verification._public_key = None  # vide le cache de la clé


@pytest.fixture
def make_token(rsa_keys):
    def _make(role, user_id=None, expired=False):
        now = dt.datetime.now(dt.timezone.utc)
        payload = {
            "sub": str(user_id or uuid.uuid4()),
            "role": role,
            "iat": now,
            "exp": now + dt.timedelta(hours=-1 if expired else 1),
        }
        return jwt.encode(payload, rsa_keys["private"], algorithm="RS256")

    return _make


@pytest.fixture
def client_for(make_token):
    def _client(role=None, user_id=None, token=None):
        client = APIClient()
        token = token or (make_token(role, user_id) if role else None)
        if token:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    return _client


@pytest.fixture
def as_anon(client_for):
    return client_for()


@pytest.fixture
def as_admin(client_for):
    return client_for("admin")


@pytest.fixture
def as_supervisor(client_for):
    return client_for("supervisor")


@pytest.fixture
def as_teacher(client_for):
    return client_for("teacher")


@pytest.fixture
def as_student(client_for):
    return client_for("student")


# ------------------------------------------------------------------ RabbitMQ simulé
@pytest.fixture(autouse=True)
def published(monkeypatch):
    """Aucun message réel : les événements publiés sont enregistrés dans une liste."""
    events = []

    def fake_publish(routing_key, data):
        events.append((routing_key, data))
        return True

    monkeypatch.setattr("core.messaging.publisher.publish", fake_publish)
    return events


@pytest.fixture
def capture(django_capture_on_commit_callbacks):
    """with capture(): ... exécute les callbacks on_commit (donc la publication)."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


# ------------------------------------------------------------------ données
@pytest.fixture
def make_user():
    def _make(role="student", **extra):
        n = next(_counter)
        group_id = extra.pop("group_id", None)
        matricule = extra.pop("matricule", f"M{n:06d}")
        user = User.objects.create(
            email=extra.pop("email", f"{role}{n}@test.dz"),
            first_name=extra.pop("first_name", "Prenom"),
            last_name=extra.pop("last_name", f"Nom{n}"),
            role=role,
            **extra,
        )
        if role == "student":
            StudentProfile.objects.create(user=user, matricule=matricule, group_id=group_id)
        elif role == "teacher":
            TeacherProfile.objects.create(user=user, grade="MCB")
        return user

    return _make


@pytest.fixture
def student_payload():
    def _build(**over):
        n = next(_counter)
        data = {
            "email": f"new.student{n}@test.dz",
            "first_name": "Sara",
            "last_name": "Test",
            "role": "student",
            "student_profile": {"matricule": f"N{n:06d}"},
        }
        data.update(over)
        return data

    return _build


@pytest.fixture
def teacher_payload():
    def _build(**over):
        n = next(_counter)
        data = {
            "email": f"new.teacher{n}@test.dz",
            "first_name": "Karim",
            "last_name": "Test",
            "role": "teacher",
            "teacher_profile": {"grade": "MCA"},
        }
        data.update(over)
        return data

    return _build
