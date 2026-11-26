import json
import pika

RABBITMQ_HOST = '127.0.0.1'
QUEUE_NAME = 'notifications_queue'

def send_test_alert():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    payload = {
        "etudiant_id": 1,
        "etudiant_nom": "Haouchine Sara",
        "etudiant_email": "sara@univ-boumerdes.dz",
        "module_nom": "WAMS - Microservices",
        "nb_absences": 5
    }

    channel.basic_publish(
        exchange='',
        routing_key=QUEUE_NAME,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)  # Rend le message persistant
    )
    print(f"[Test Publisher] Message envoyé dans '{QUEUE_NAME}' : {payload}")
    connection.close()

if __name__ == '__main__':
    send_test_alert()
    