"""Simule S3 (Academic) : publie des événements academic.* sur RabbitMQ pour tester le CONSOMMATEUR de S4.
   python tools/fake_s3.py --url amqp://guest:guest@localhost:5672/%2F --students 6
Ensuite : GET /api/attendance/v1/seances/today/ (enseignant 'teacher-1') doit montrer la séance créée."""
import argparse
import datetime as dt
import json
import uuid

import pika

p = argparse.ArgumentParser()
p.add_argument("--url", default="amqp://guest:guest@localhost:5672/%2F")
p.add_argument("--students", type=int, default=6)
p.add_argument("--teacher", default="teacher-1")
a = p.parse_args()

conn = pika.BlockingConnection(pika.URLParameters(a.url))
ch = conn.channel()
ch.exchange_declare(exchange="unitrack.events", exchange_type="topic", durable=True)


def publish(rk, data):
    ch.basic_publish("unitrack.events", rk, json.dumps({"event_id": str(uuid.uuid4()), "event_type": rk, "version": 1,
                     "source": "academic-service", "data": data}).encode(),
                     pika.BasicProperties(content_type="application/json", delivery_mode=2, message_id=str(uuid.uuid4())))
    print("→", rk)


for i in range(1, a.students + 1):
    publish("academic.enrollment.upserted.v1", {"student_id": f"student-{i}", "group_id": "G1", "matricule": f"2026{i:04d}",
            "first_name": f"Prenom{i}", "last_name": f"Nom{i}", "email": f"student-{i}@univ-boumerdes.dz"})
now = dt.datetime.now()
publish("academic.seance.upserted.v1", {
    "id": f"s3-{uuid.uuid4().hex[:6]}", "module": {"id": "M1", "name": "Génie Logiciel", "semester": "S1"},
    "group": {"id": "G1", "label": "Groupe 1"}, "teacher": {"id": a.teacher, "name": "Dr. Demo"},
    "room": {"id": "R1", "name": "Salle 101"}, "date": now.date().isoformat(),
    "start_time": (now - dt.timedelta(minutes=5)).strftime("%H:%M"), "end_time": (now + dt.timedelta(minutes=85)).strftime("%H:%M"),
    "type": "TD"})
conn.close()
