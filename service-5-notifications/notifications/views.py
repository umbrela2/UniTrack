from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import NotificationHistory, NotificationPreference

@api_view(['POST'])
def send_absence_alert(request):
    """
    Reçoit le nombre d'absences depuis le Service 3 (Présences)
    et déclenche une alerte Orange (3 abs) ou Rouge (5 abs).
    """
    data = request.data
    etudiant_id = data.get('etudiant_id')
    etudiant_nom = data.get('etudiant_nom')
    etudiant_email = data.get('etudiant_email')
    module_nom = data.get('module_nom')
    nb_absences = int(data.get('nb_absences', 0))

    if nb_absences < 3:
        return Response({"status": "ignored", "detail": "Moins de 3 absences, aucune alerte requise."}, status=200)

    if 3 <= nb_absences < 5:
        niveau = 'WARNING'
        sujet = f"[UniTrack] Alerte Orange : {nb_absences} absences en {module_nom}"
        message = f"Bonjour {etudiant_nom}, vous avez atteint {nb_absences} absences dans le module {module_nom}. Attention au seuil d'exclusion (5 absences)."
    else:
        niveau = 'DANGER'
        sujet = f"[UniTrack] ALERTE ROUGE (Exclusion) : {nb_absences} absences en {module_nom}"
        message = f"Bonjour {etudiant_nom}, vous avez atteint {nb_absences} absences en {module_nom}. Vous avez atteint le seuil d'exclusion."

    
    notif_in_app = NotificationHistory.objects.create(
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

    
    statut_email = 'SENT'
    try:
        send_mail(
            subject=sujet,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[etudiant_email],
            fail_silently=False,
        )
    except Exception:
        statut_email = 'FAILED'

    NotificationHistory.objects.create(
        etudiant_id=etudiant_id,
        etudiant_nom=etudiant_nom,
        etudiant_email=etudiant_email,
        module_nom=module_nom,
        nb_absences=nb_absences,
        niveau=niveau,
        canal='EMAIL',
        statut=statut_email,
        sujet=sujet,
        message=message
    )

    return Response({
        "status": "success",
        "id": notif_in_app.id,
        "niveau": niveau,
        "email_status": statut_email,
        "message": message
    }, status=201)


@api_view(['GET'])
def student_notifications(request, etudiant_id):
    """
    Retourne l'historique des alertes d'un étudiant.
    """
    notifs = NotificationHistory.objects.filter(etudiant_id=etudiant_id).order_by('-date_creation')
    data = list(notifs.values(
        'id', 'module_nom', 'nb_absences', 'niveau', 'canal', 'statut', 'sujet', 'message', 'date_creation'
    ))
    return Response(data, status=200)