import pytest

pytestmark = pytest.mark.django_db
URL = "/api/users/"


def test_health_is_public(as_anon):
    response = as_anon.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_no_token_is_401(as_anon):
    assert as_anon.get(URL).status_code == 401


def test_garbage_token_is_401(client_for):
    assert client_for(token="pas.un.jwt").get(URL).status_code == 401


def test_expired_token_is_401(client_for, make_token):
    token = make_token("admin", expired=True)
    assert client_for(token=token).get(URL).status_code == 401


def test_unknown_role_is_401(client_for):
    assert client_for("hacker").get(URL).status_code == 401


@pytest.mark.parametrize("fixture_name", ["as_student", "as_teacher"])
def test_student_and_teacher_cannot_list_users(request, fixture_name):
    client = request.getfixturevalue(fixture_name)
    assert client.get(URL).status_code == 403


def test_student_cannot_read_another_user(as_student, make_user):
    other = make_user("student")
    assert as_student.get(f"{URL}{other.id}/").status_code == 403


def test_admin_can_list(as_admin):
    assert as_admin.get(URL).status_code == 200


def test_supervisor_is_read_only(as_supervisor, make_user, student_payload):
    user = make_user("student")
    assert as_supervisor.get(URL).status_code == 200
    assert as_supervisor.get(f"{URL}{user.id}/").status_code == 200
    assert as_supervisor.post(URL, student_payload(), format="json").status_code == 403
    assert as_supervisor.patch(f"{URL}{user.id}/", {"phone": "1"}, format="json").status_code == 403
    assert as_supervisor.delete(f"{URL}{user.id}/").status_code == 403
    assert as_supervisor.patch(f"{URL}{user.id}/deactivate/").status_code == 403
