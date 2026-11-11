from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import NotificationHistory, NotificationPreference


def home_dashboard(request):
    notifs = NotificationHistory.objects.all().order_by('-date_creation')
    rows = ""
    for n in notifs:
        badge_niv = "bg-warning text-dark" if n.niveau == "WARNING" else "bg-danger"
        badge_stat = "bg-success" if n.statut == "SENT" else ("bg-info text-dark" if n.statut == "READ" else "bg-secondary")
        rows += f"""
        <tr>
            <td><strong>#{n.etudiant_id}</strong> - {n.etudiant_nom}</td>
            <td>{n.module_nom}</td>
            <td><span class="badge bg-secondary">{n.nb_absences} absences</span></td>
            <td><span class="badge {badge_niv}">{n.get_niveau_display()}</span></td>
            <td>{n.canal}</td>
            <td><span class="badge {badge_stat}">{n.statut}</span></td>
            <td>{n.date_creation.strftime('%d/%m/%Y %H:%M')}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="7" class="text-center text-muted py-4">Aucune alerte enregistrée pour le moment. Testez l\'API !</td></tr>'

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>UniTrack - Service 5 : Notifications & Alertes</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <div class="row mb-4">
                <div class="col-12 text-center">
                    <h1 class="fw-bold text-primary">UniTrack : Système de Suivi d'Assiduité</h1>
                    <p class="text-muted">Service 5 - Notifications, Alertes et Gestion des Seuils (Port 8005)</p>
                </div>
            </div>

            <div class="card shadow-sm border-0 mb-4">
                <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">API Endpoints Disponibles</h5>
                    <span class="badge bg-success">En ligne</span>
                </div>
                <div class="card-body">
                    <ul class="mb-0">
                        <li><code>POST</code> <a href="/api/notifications/alert/"><strong>/api/notifications/alert/</strong></a> : Déclencher une alerte (3 ou 5 absences)</li>
                        <li><code>GET</code> <a href="/api/notifications/student/1/"><strong>/api/notifications/student/1/</strong></a> : Historique des alertes de l'étudiant #1</li>
                        <li><code>POST</code> <a href="/api/notifications/preferences/"><strong>/api/notifications/preferences/</strong></a> : Mettre à jour les préférences (Email / In-App / Push)</li>
                        <li><code>POST</code> <strong>/api/notifications/read/&lt;id&gt;/</strong> : Marquer une notification comme lue (READ)</li>
                    </ul>
                </div>
            </div>

            <div class="card shadow-sm border-0">
                <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">Journal des Alertes et Historique</h5>
                    <span class="badge bg-light text-primary">Temps Réel</span>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light">
                                <tr>
                                    <th>Étudiant</th>
                                    <th>Module</th>
                                    <th>Absences</th>
                                    <th>Niveau d'Alerte</th>
                                    <th>Canal</th>
                                    <th>Statut</th>
                                    <th>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


@api_view(['POST'])
def send_absence_alert(request):
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
    notifs = NotificationHistory.objects.filter(etudiant_id=etudiant_id).order_by('-date_creation')
    data = list(notifs.values(
        'id', 'module_nom', 'nb_absences', 'niveau', 'canal', 'statut', 'sujet', 'message', 'date_creation'
    ))
    return Response(data, status=200)


@api_view(['POST'])
def update_preferences(request):
    data = request.data
    user_id = data.get('user_id')
    user_email = data.get('user_email', 'etudiant@univ-boumerdes.dz')

    pref, _ = NotificationPreference.objects.get_or_create(
        user_id=user_id,
        defaults={'user_email': user_email}
    )

    pref.receive_email = data.get('receive_email', pref.receive_email)
    pref.receive_in_app = data.get('receive_in_app', pref.receive_in_app)
    pref.receive_push = data.get('receive_push', pref.receive_push)
    pref.save()

    return Response({"status": "success", "message": "Préférences mises à jour avec succès."}, status=200)


@api_view(['POST'])
def mark_as_read(request, notif_id):
    try:
        notif = NotificationHistory.objects.get(id=notif_id)
        notif.statut = 'READ'
        notif.save()
        return Response({"status": "success", "message": "Notification marquée comme lue."}, status=200)
    except NotificationHistory.DoesNotExist:
        return Response({"error": "Notification introuvable."}, status=404)