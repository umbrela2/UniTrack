import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import Enrollment, Seance


class Command(BaseCommand):
    help = "Données de démonstration (sans S2/S3) : 1 groupe, N étudiants, 3 séances aujourd'hui pour teacher-1."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=8)

    def handle(self, *args, **o):
        for i in range(1, o["students"] + 1):
            Enrollment.objects.update_or_create(
                student_id=f"student-{i}", group_id="G1",
                defaults={"matricule": f"20260{i:04d}", "nom": f"Nom{i}", "prenom": f"Prenom{i}",
                          "email": f"student-{i}@univ-boumerdes.dz"})
        now = timezone.localtime()
        today = now.date()
        base = now.replace(second=0, microsecond=0)
        plan = [("demo-1", "M1", "Génie Logiciel", -10, 80), ("demo-2", "M2", "Base de données", 120, 210),
                ("demo-3", "M1", "Génie Logiciel", -300, -210)]       # la 3e est passée → sera « non assurée »
        for sid, mod, name, a, b in plan:
            start, end = base + dt.timedelta(minutes=a), base + dt.timedelta(minutes=b)
            if start.date() != today or end.date() != today:
                start, end = base.replace(hour=8, minute=0), base.replace(hour=9, minute=30)
            Seance.objects.update_or_create(academic_seance_id=sid, defaults={
                "module_id": mod, "module_intitule": name, "semestre": "S1", "group_id": "G1", "group_label": "Groupe 1",
                "enseignant_id": "teacher-1", "enseignant_nom": "Dr. Demo", "salle_id": "R1", "salle_nom": "Salle 101",
                "date_seance": today, "heure_debut": start.time(), "heure_fin": end.time(), "type_seance": "TD",
                "statut": "PLANIFIEE", "code_presence": "", "code_expires_at": None})
        self.stdout.write(self.style.SUCCESS("Données de démo créées. Utilisateurs : teacher-1, student-1…student-N."))
