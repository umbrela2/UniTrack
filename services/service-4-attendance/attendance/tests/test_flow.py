import datetime as dt

import pytest
from django.utils import timezone

from attendance import handlers, services
from attendance.models import (AttendanceSettings, OutboxEvent, Presence, PresenceStatus, Seance, SeanceStatus)

from .conftest import client_for, make_seance, student

BASE = "/api/attendance/v1"
pytestmark = pytest.mark.django_db


def start(teacher, s):
    r = teacher.post(f"{BASE}/seances/{s.id}/start/")
    assert r.status_code == 200, r.content
    return r.data["code"]


def rks():
    return list(OutboxEvent.objects.order_by("created_at").values_list("routing_key", flat=True))


def test_auth_required_and_roles(group, teacher):
    s = make_seance()
    from rest_framework.test import APIClient
    assert APIClient().get(f"{BASE}/seances/today/").status_code == 401
    bad = APIClient(); bad.credentials(HTTP_AUTHORIZATION="Bearer nope")
    assert bad.get(f"{BASE}/seances/today/").status_code == 401
    assert student(1).post(f"{BASE}/seances/{s.id}/start/").status_code == 403           # RG14
    assert student(1).get(f"{BASE}/history/").status_code == 403
    assert teacher.get(f"{BASE}/settings/").status_code == 403


def test_start_rules(group, teacher):
    s = make_seance()
    assert client_for("teacher-2", "ENSEIGNANT").post(f"{BASE}/seances/{s.id}/start/").status_code == 403
    code = start(teacher, s)
    assert len(code) == 6 and code.isdigit()
    assert teacher.post(f"{BASE}/seances/{s.id}/start/").status_code == 409
    future = make_seance(start_offset=300, sid="future")
    assert teacher.post(f"{BASE}/seances/{future.id}/start/").data["error"] == "too_early"


def test_check_in_rules(group, teacher):
    s = make_seance()
    url = f"{BASE}/seances/{s.id}/check-in/"
    assert student(1).post(url, {"code": "000000"}).data["error"] == "session_not_active"
    code = start(teacher, s)
    assert student(1).post(url, {"code": "abc"}).data["error"] == "invalid_code"
    assert student(1).post(url, {"code": code}).status_code == 201
    assert student(1).post(url, {"code": code}).status_code == 409                      # RG1
    assert client_for("student-99", "ETUDIANT").post(url, {"code": code}).data["error"] == "not_in_group"   # RG3
    Seance.objects.filter(pk=s.pk).update(code_expires_at=timezone.now() - dt.timedelta(seconds=1))
    r = student(2).post(url, {"code": code})
    assert r.status_code == 410 and r.data["error"] == "code_expired"                  # RG2
    new = teacher.post(f"{BASE}/seances/{s.id}/regenerate-code/").data["code"]
    assert student(2).post(url, {"code": new}).status_code == 201
    assert rks().count("attendance.recorded.v1") == 2


def test_student_never_sees_code(group, teacher):
    s = make_seance()
    start(teacher, s)
    assert "code" not in student(1).get(f"{BASE}/seances/{s.id}/").data
    assert student(1).get(f"{BASE}/seances/{s.id}/code/").status_code == 403
    assert [x["id"] for x in student(1).get(f"{BASE}/seances/current/").data] == [s.id]


def test_manual_and_close(group, teacher):
    s = make_seance()
    code = start(teacher, s)
    student(1).post(f"{BASE}/seances/{s.id}/check-in/", {"code": code})
    r = teacher.put(f"{BASE}/seances/{s.id}/presences/student-2/", {"statut": "PRESENT"}, format="json")
    assert r.status_code == 200 and r.data["mode"] == "MANUEL"
    assert teacher.put(f"{BASE}/seances/{s.id}/presences/zzz/", {"statut": "PRESENT"}, format="json").status_code == 404
    roster = teacher.get(f"{BASE}/seances/{s.id}/presences/").data
    assert roster["summary"] == {"total": 5, "presents": 2, "absents": 0, "en_attente": 3}
    closed = teacher.post(f"{BASE}/seances/{s.id}/close/").data
    assert closed["summary"] == {"total": 5, "presents": 2, "absents": 3, "en_attente": 0}
    assert Presence.objects.filter(seance=s, mode="AUTO").count() == 3
    assert teacher.post(f"{BASE}/seances/{s.id}/close/").status_code == 409
    assert teacher.put(f"{BASE}/seances/{s.id}/presences/student-3/", {"statut": "PRESENT"}, format="json").status_code == 409
    assert "attendance.session.closed.v1" in rks()
    assert teacher.get(f"{BASE}/seances/{s.id}/export/").status_code == 200


def test_threshold_alert(group, teacher):
    for i in range(2):                                                                   # 2 absences antérieures
        old = make_seance(sid=f"old{i}")
        old.statut = SeanceStatus.CLOTUREE; old.save()
        Presence.objects.create(seance=old, student_id="student-5", statut="ABSENT", mode="AUTO")
    s = make_seance(sid="third")
    start(teacher, s)
    teacher.post(f"{BASE}/seances/{s.id}/close/")
    ev = OutboxEvent.objects.get(routing_key="attendance.absence_threshold_reached.v1",
                                 payload__data__student_id="student-5")
    assert ev.payload["data"]["level"] == "orange" and ev.payload["data"]["absences_count"] == 3
    summary = student(5).get(f"{BASE}/me/attendance/").data
    assert summary["modules"][0]["niveau_alerte"] == "orange"
    assert len(student(5).get(f"{BASE}/me/alerts/").data["alertes"]) == 1


def test_teacher_absent_detection(group):
    s = make_seance()
    assert services.declare_missed_sessions(now=s.end_dt - dt.timedelta(minutes=1)) == 0     # séance pas encore finie
    assert services.declare_missed_sessions(now=s.end_dt + dt.timedelta(minutes=1)) == 1
    s.refresh_from_db()
    assert s.statut == SeanceStatus.NON_ASSUREE
    assert Presence.objects.count() == 0                                                 # étudiants non comptés absents
    assert "attendance.session.not_held.v1" in rks()
    assert services.declare_missed_sessions(now=s.end_dt + dt.timedelta(minutes=2)) == 0
    admin = client_for("admin-1", "ADMIN")
    assert admin.get(f"{BASE}/seances/non-assurees/").data["count"] == 1


def test_auto_close_stale(group, teacher):
    s = make_seance()
    start(teacher, s)
    assert services.auto_close_stale_sessions(now=s.end_dt + dt.timedelta(minutes=10)) == 0
    assert services.auto_close_stale_sessions(now=s.end_dt + dt.timedelta(minutes=31)) == 1
    assert Presence.objects.filter(seance=s, statut="ABSENT").count() == 5


def test_geo_check(group, teacher):
    cfg = AttendanceSettings.get()
    cfg.geo_check_enabled, cfg.geo_latitude, cfg.geo_longitude, cfg.geo_radius_m = True, 36.7538, 3.0588, 200
    cfg.save()
    s = make_seance()
    code = start(teacher, s)
    url = f"{BASE}/seances/{s.id}/check-in/"
    assert student(1).post(url, {"code": code}).data["error"] == "location_required"
    assert student(1).post(url, {"code": code, "latitude": 36.9, "longitude": 3.0}, format="json").data["error"] == "out_of_range"
    assert student(1).post(url, {"code": code, "latitude": 36.7539, "longitude": 3.0589}, format="json").status_code == 201


def test_admin_settings_and_history(group, admin, teacher):
    assert admin.put(f"{BASE}/settings/", {"threshold_warning": 6}, format="json").status_code == 400
    assert admin.put(f"{BASE}/settings/", {"threshold_warning": 2, "threshold_critical": 4}, format="json").status_code == 200
    s = make_seance()
    start(teacher, s)
    teacher.post(f"{BASE}/seances/{s.id}/close/")
    r = admin.get(f"{BASE}/history/", {"group_id": "G1", "statut": "ABSENT"})
    assert r.status_code == 200 and r.data["count"] == 5 and r.data["results"][0]["student_nom"]
    assert admin.get(f"{BASE}/dashboard/").status_code == 200
    assert teacher.get(f"{BASE}/dashboard/").data["seances_par_statut"]["CLOTUREE"] == 1


def test_handlers_idempotent(db):
    payload = {"id": "77", "module": {"id": "M9", "name": "Réseaux", "semester": "S2"}, "group": {"id": "G9", "label": "G9"},
               "teacher": {"id": "t9", "name": "Dr 9"}, "room": {"id": "r", "name": "R1"},
               "date": "2026-11-20", "start_time": "08:30", "end_time": "10:00", "type": "TP"}
    for _ in range(2):
        handlers.dispatch("academic.seance.upserted.v1", payload)
        handlers.dispatch("academic.enrollment.upserted.v1", {"student_id": "s1", "group_id": "G9", "email": "a@b.dz"})
    assert Seance.objects.filter(academic_seance_id="77").count() == 1
    handlers.dispatch("academic.seance.deleted.v1", {"id": "77"})
    assert not Seance.objects.filter(academic_seance_id="77").exists()


def test_concurrent_double_submit_is_single_presence(group, teacher):
    s = make_seance()
    code = start(teacher, s)
    codes = [student(1).post(f"{BASE}/seances/{s.id}/check-in/", {"code": code}).status_code for _ in range(3)]
    assert codes == [201, 409, 409] and Presence.objects.filter(seance=s).count() == 1


def test_health(client, db):
    r = client.get("/health/")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"
