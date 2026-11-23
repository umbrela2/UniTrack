"""FP12 / UC-SYS-02 : declare 'Non assuree' les seances PLANIFIEE dont l'horaire
est termine sans demarrage. A lancer chaque minute :

    * * * * * cd /chemin/service-3-academic && venv/bin/python manage.py declare_absences

Les etudiants ne sont PAS comptes absents (la seance est non assuree).
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Q

from academics.models import Seance
from academics.notify import send_event


class Command(BaseCommand):
    help = "Declare les seances non demarrees comme 'Non assuree'."

    def handle(self, *args, **opts):
        now = datetime.now()
        qs = Seance.objects.filter(statut=Seance.Statut.PLANIFIEE).filter(
            Q(date_seance__lt=now.date())
            | Q(date_seance=now.date(), heure_fin__lt=now.time())
        )
        n = 0
        for s in qs.select_related("module", "groupe"):
            updated = Seance.objects.filter(
                pk=s.pk, statut=Seance.Statut.PLANIFIEE
            ).update(statut=Seance.Statut.NON_ASSUREE)
            if updated:  # evite un doublon si le Service 4 vient de la demarrer
                n += 1
                send_event("seance.non_assuree", {
                    "seance_id": s.pk,
                    "enseignant_id": s.enseignant_id,
                    "groupe_id": s.groupe_id,
                    "module": s.module.intitule,
                    "date": s.date_seance.isoformat(),
                })
        self.stdout.write(self.style.SUCCESS(f"{n} seance(s) declaree(s) non assuree(s)."))
