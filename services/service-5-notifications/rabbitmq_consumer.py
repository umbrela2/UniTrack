import os
import json
import django
import pika

# Initialiser l'environnement Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings
from notifications.models import NotificationHistory

RABBITMQ_URL = os.getenv('RABBITMQ_URL')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', '127.0.0.1')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', '5672'))
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '/')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'guest')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'unitrack.events')
QUEUE_NAME = os.getenv('RABBITMQ_QUEUE', 'notifications_queue')
ROUTING_KEYS = (
    'attendance.absence_threshold_reached.*',
    'attendance.session.not_held.*',
)


def _connection():
    if RABBITMQ_URL:
        return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST,
            credentials=credentials,
        )
    )


def process_absence_event(ch, method, properties, body):
    payload = json.loads(body)
    data = payload.get('data', payload) if isinstance(payload, dict) else {}
    print(f"[RabbitMQ] Message reçu : {data}")

    etudiant_id = data.get('etudiant_id', data.get('student_id'))
    etudiant_nom = data.get('etudiant_nom') or data.get('student_name') or ''
    etudiant_email = data.get('etudiant_email') or data.get('student_email') or ''
    module_nom = data.get('module_nom') or data.get('module_intitule') or ''
    nb_absences = int(data.get('nb_absences') or data.get('absences_count') or 0)

    if nb_absences >= 3:
        niveau = 'WARNING' if nb_absences < 5 else 'DANGER'
        sujet = f"[UniTrack] {'Alerte Orange' if niveau == 'WARNING' else 'ALERTE ROUGE'} : {nb_absences} absences en {module_nom}"
        message = f"Bonjour {etudiant_nom}, vous avez atteint {nb_absences} absences dans le module {module_nom}."

        NotificationHistory.objects.create(
            etudiant_id=etudiant_id,
            etudiant_nom=etudiant_nom,
            etudiant_email=etudiant_email,
            module_nom=module_nom,
            nb_absences=nb_absences,
            niveau=niveau,
            canal='IN_APP',
            statut='SENT',
            sujet=sujet,
            message=message
        )
        print(f"[RabbitMQ] Notification enregistrée en base pour {etudiant_nom} ({niveau})")

    ch.basic_ack(delivery_tag=method.delivery_tag)

def start_consuming():
    connection = _connection()
    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    for routing_key in ROUTING_KEYS:
        channel.queue_bind(queue=QUEUE_NAME, exchange=EXCHANGE_NAME, routing_key=routing_key)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_absence_event)
    print(f"[RabbitMQ] En attente de messages sur '{QUEUE_NAME}' (exchange: {EXCHANGE_NAME})...")
    channel.start_consuming()

if __name__ == '__main__':
    start_consuming()