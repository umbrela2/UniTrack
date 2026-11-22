import uuid

import pytest

from users.handlers import handle_group_deleted
from users.models import StudentProfile

pytestmark = pytest.mark.django_db
URL = "/api/users/"


def names(published):
    return [routing_key for routing_key, _ in published]


def test_create_publishes_user_created(as_admin, student_payload, published, capture):
    payload = student_payload()
    with capture():
        response = as_admin.post(URL, payload, format="json")
    assert response.status_code == 201
    assert names(published) == ["user.created"]
    data = published[0][1]
    assert data["email"] == payload["email"]
    assert data["role"] == "student"
    assert data["student"]["matricule"] == payload["student_profile"]["matricule"]
    # minimisation des données (loi 18-07)
    assert "phone" not in data
    assert "date_of_birth" not in str(data)


def test_update_publishes_user_updated(as_admin, make_user, published, capture):
    user = make_user("student")
    with capture():
        as_admin.patch(f"{URL}{user.id}/", {"last_name": "Nouveau"}, format="json")
    assert names(published) == ["user.updated"]
    assert published[0][1]["last_name"] == "Nouveau"


def test_lifecycle_events(as_admin, make_user, published, capture):
    user = make_user("teacher")
    with capture():
        as_admin.patch(f"{URL}{user.id}/deactivate/")
        as_admin.patch(f"{URL}{user.id}/activate/")
        as_admin.delete(f"{URL}{user.id}/")
        as_admin.post(f"{URL}{user.id}/restore/")
    assert names(published) == [
        "user.deactivated", "user.activated", "user.deleted", "user.activated",
    ]


def test_no_event_when_validation_fails(as_admin, student_payload, published, capture):
    payload = student_payload()
    del payload["student_profile"]
    with capture():
        assert as_admin.post(URL, payload, format="json").status_code == 400
    assert published == []


# ------------------------------------------------------------------ événement reçu
def test_group_deleted_clears_group_and_notifies(make_user, published, capture):
    group, other = uuid.uuid4(), uuid.uuid4()
    a = make_user("student", group_id=group)
    b = make_user("student", group_id=group)
    c = make_user("student", group_id=other)
    with capture():
        handle_group_deleted({"group_id": str(group)})
    assert StudentProfile.objects.get(user=a).group_id is None
    assert StudentProfile.objects.get(user=b).group_id is None
    assert StudentProfile.objects.get(user=c).group_id == other
    assert names(published) == ["user.updated", "user.updated"]
    assert all(data["student"]["group_id"] is None for _, data in published)


def test_group_deleted_is_idempotent(make_user, published, capture):
    group = uuid.uuid4()
    make_user("student", group_id=group)
    with capture():
        handle_group_deleted({"group_id": str(group)})
        handle_group_deleted({"group_id": str(group)})  # même événement rejoué
    assert names(published) == ["user.updated"]


@pytest.mark.parametrize("data", [{}, {"group_id": "pas-un-uuid"}, {"group_id": None}])
def test_group_deleted_with_bad_payload_is_ignored(data, published, capture):
    with capture():
        handle_group_deleted(data)  # ne doit pas lever d'exception
    assert published == []
