"""Test de charge FC3 / FP6 : N étudiants saisissent le code en même temps.

Préparation :  python manage.py seed_demo --students 200   puis démarrer la séance demo-1 (récupérer SEANCE_ID et CODE).
Lancement   :  SEANCE_ID=1 CODE=123456 JWT_SECRET=... locust -f loadtest/locustfile.py --host http://localhost \
                   --users 200 --spawn-rate 200 --run-time 30s --headless
Objectif    :  200 saisies simultanées, temps de réponse < 2 s, 0 erreur 5xx (les 409 « déjà enregistré » sont normaux).
"""
import itertools
import os
import time

import jwt
from locust import HttpUser, between, task

counter = itertools.count(1)
SECRET = os.environ.get("JWT_SECRET", "dev-shared-secret-change-me")
SEANCE_ID = os.environ["SEANCE_ID"]
CODE = os.environ["CODE"]


class Student(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        sub = f"student-{next(counter)}"
        token = jwt.encode({"sub": sub, "role": "ETUDIANT", "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")
        self.client.headers["Authorization"] = f"Bearer {token}"

    @task(3)
    def check_in(self):
        with self.client.post(f"/api/attendance/v1/seances/{SEANCE_ID}/check-in/", json={"code": CODE},
                              name="check-in", catch_response=True) as r:
            if r.status_code in (201, 409):
                r.success()

    @task(1)
    def my_attendance(self):
        self.client.get("/api/attendance/v1/me/attendance/", name="me/attendance")
