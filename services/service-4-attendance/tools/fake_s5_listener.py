"""Simule S5 (Notifications) : écoute les événements publiés par S4 et les affiche → PREUVE du flux asynchrone.
   python tools/fake_s5_listener.py --url amqp://guest:guest@localhost:5672/%2F
Montre : producteur (S4) → exchange 'unitrack.events' → queue → consommateur."""
import argparse
import json

import pika

p = argparse.ArgumentParser()
p.add_argument("--url", default="amqp://guest:guest@localhost:5672/%2F")
a = p.parse_args()
conn = pika.BlockingConnection(pika.URLParameters(a.url))
ch = conn.channel()
ch.exchange_declare(exchange="unitrack.events", exchange_type="topic", durable=True)
q = ch.queue_declare(queue="notifications.attendance_events.demo", durable=True).method.queue
ch.queue_bind(q, "unitrack.events", "attendance.#")


def on(ch_, m, props, body):
    ev = json.loads(body)
    d = ev["data"]
    if m.routing_key.startswith("attendance.absence_threshold_reached"):
        print(f"📧 E-MAIL à {d['student_email']} : {d['absences_count']} absences en {d['module_intitule']} → niveau {d['level'].upper()}")
    else:
        print(f"[{m.routing_key}] {json.dumps(d, ensure_ascii=False)[:160]}")
    ch_.basic_ack(m.delivery_tag)


ch.basic_consume(q, on)
print("En écoute sur attendance.# … (Ctrl+C pour arrêter)")
ch.start_consuming()
