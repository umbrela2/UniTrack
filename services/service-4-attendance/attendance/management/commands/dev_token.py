import time

import jwt
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Génère un JWT de développement (simule S1 Auth). Ex: dev_token --role ENSEIGNANT --sub teacher-1"

    def add_arguments(self, parser):
        parser.add_argument("--role", required=True, choices=["ADMIN", "SUPERVISEUR", "ENSEIGNANT", "ETUDIANT"])
        parser.add_argument("--sub", required=True)
        parser.add_argument("--hours", type=int, default=12)

    def handle(self, *args, **o):
        claims = {"sub": o["sub"], "role": o["role"], "email": f"{o['sub']}@univ-boumerdes.dz",
                  "iat": int(time.time()), "exp": int(time.time()) + o["hours"] * 3600}
        self.stdout.write(jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM))
