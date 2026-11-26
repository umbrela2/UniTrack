import pytest

from users.models import User

pytestmark = pytest.mark.django_db
URL = "/api/users/"


# ------------------------------------------------------------------ création
def test_admin_creates_student(as_admin, student_payload):
    payload = student_payload()
    response = as_admin.post(URL, payload, format="json")
    assert response.status_code == 201, response.data
    assert response.data["role"] == "student"
    assert response.data["student_profile"]["matricule"] == payload["student_profile"]["matricule"]
    assert User.objects.filter(email=payload["email"]).exists()


def test_admin_creates_teacher(as_admin, teacher_payload):
    response = as_admin.post(URL, teacher_payload(), format="json")
    assert response.status_code == 201, response.data
    assert response.data["teacher_profile"]["grade"] == "MCA"


def test_admin_creates_admin_without_profile(as_admin):
    payload = {"email": "chef@test.dz", "first_name": "Chef", "last_name": "Dept", "role": "admin"}
    assert as_admin.post(URL, payload, format="json").status_code == 201


def test_student_without_profile_is_rejected(as_admin, student_payload):
    payload = student_payload()
    del payload["student_profile"]
    response = as_admin.post(URL, payload, format="json")
    assert response.status_code == 400
    assert "student_profile" in response.data


def test_student_with_teacher_profile_is_rejected(as_admin, student_payload):
    payload = student_payload(teacher_profile={"grade": "MCA"})
    assert as_admin.post(URL, payload, format="json").status_code == 400


def test_duplicate_email_is_rejected(as_admin, student_payload):
    first = student_payload()
    assert as_admin.post(URL, first, format="json").status_code == 201
    second = student_payload(email=first["email"].upper())  # insensible à la casse
    response = as_admin.post(URL, second, format="json")
    assert response.status_code == 400
    assert "email" in response.data


def test_duplicate_matricule_is_rejected(as_admin, student_payload):
    first = student_payload()
    assert as_admin.post(URL, first, format="json").status_code == 201
    second = student_payload(student_profile={"matricule": first["student_profile"]["matricule"]})
    assert as_admin.post(URL, second, format="json").status_code == 400


# ------------------------------------------------------------------ modification
def test_role_cannot_change(as_admin, make_user):
    user = make_user("student")
    response = as_admin.patch(f"{URL}{user.id}/", {"role": "teacher"}, format="json")
    assert response.status_code == 400
    assert "role" in response.data


def test_put_accepts_null_profile_of_other_role(as_admin, make_user):
    """Régression : le corps d'un GET (avec student_profile: null) doit être renvoyable en PUT."""
    teacher = make_user("teacher")
    body = dict(as_admin.get(f"{URL}{teacher.id}/").data)
    assert body["student_profile"] is None
    body["last_name"] = "Changed"
    response = as_admin.put(f"{URL}{teacher.id}/", body, format="json")
    assert response.status_code == 200, response.data
    teacher.refresh_from_db()
    assert teacher.last_name == "Changed"


# ------------------------------------------------------------------ lecture / filtres
def test_list_filters(as_admin, make_user):
    make_user("student", first_name="Amine")
    make_user("teacher")
    assert as_admin.get(URL).data["count"] == 2
    assert as_admin.get(URL, {"role": "student"}).data["count"] == 1
    assert as_admin.get(URL, {"q": "amine"}).data["count"] == 1


def test_students_and_teachers_endpoints(as_admin, make_user):
    make_user("student")
    make_user("student")
    make_user("teacher")
    assert as_admin.get("/api/students/").data["count"] == 2
    assert as_admin.get("/api/teachers/").data["count"] == 1
    assert as_admin.post("/api/students/", {}, format="json").status_code == 405


# ------------------------------------------------------------------ cycle de vie
def test_deactivate_then_activate(as_admin, make_user):
    user = make_user("teacher")
    response = as_admin.patch(f"{URL}{user.id}/deactivate/")
    assert response.status_code == 200
    assert response.data["status"] == "disabled"
    response = as_admin.patch(f"{URL}{user.id}/activate/")
    assert response.data["status"] == "active"


def test_soft_delete_and_restore(as_admin, make_user):
    user = make_user("student")
    assert as_admin.delete(f"{URL}{user.id}/").status_code == 204
    assert as_admin.get(f"{URL}{user.id}/").status_code == 404
    assert as_admin.get(URL).data["count"] == 0
    assert User.all_objects.get(pk=user.id).deleted_at is not None  # toujours en base
    assert as_admin.get(URL, {"deleted": "true"}).data["count"] == 1

    response = as_admin.post(f"{URL}{user.id}/restore/")
    assert response.status_code == 200, response.data
    assert response.data["status"] == "active"
    assert as_admin.get(URL).data["count"] == 1


def test_recreating_a_deleted_email_is_rejected_with_hint(as_admin, make_user, student_payload):
    user = make_user("student", email="amine@test.dz")
    user.soft_delete()
    response = as_admin.post(URL, student_payload(email="amine@test.dz"), format="json")
    assert response.status_code == 400
    assert "supprimé" in str(response.data["email"])


# ------------------------------------------------------------------ /me/
def test_me_get_and_patch(client_for, make_user):
    user = make_user("student")
    client = client_for("student", user.id)
    response = client.get(f"{URL}me/")
    assert response.status_code == 200
    assert response.data["email"] == user.email

    response = client.patch(f"{URL}me/", {"language": "en", "phone": "0555000000"}, format="json")
    assert response.status_code == 200, response.data
    user.refresh_from_db()
    assert (user.language, user.phone) == ("en", "0555000000")


def test_me_refuses_identity_fields(client_for, make_user):
    user = make_user("student")
    response = client_for("student", user.id).patch(f"{URL}me/", {"first_name": "X"}, format="json")
    assert response.status_code == 400
    assert "first_name" in response.data


def test_me_unknown_profile_is_404(as_student):
    assert as_student.get(f"{URL}me/").status_code == 404
