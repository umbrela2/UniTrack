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

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', '127.0.0.1')  # IP du serveur RabbitMQ
QUEUE_NAME = 'notifications_queue'

def process_absence_event(ch, method, properties, body):
    data = json.loads(body)
    print(f"[RabbitMQ] Message reçu : {data}")

    etudiant_id = data.get('etudiant_id')
    etudiant_nom = data.get('etudiant_nom')
    etudiant_email = data.get('etudiant_email')
    module_nom = data.get('module_nom')
    nb_absences = int(data.get('nb_absences', 0))

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
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_absence_event)
    print(f"[RabbitMQ] En attente de messages sur '{QUEUE_NAME}' (Host: {RABBITMQ_HOST})...")
    channel.start_consuming()

if __name__ == '__main__':
    start_consuming()