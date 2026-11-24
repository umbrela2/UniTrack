"""
Génère docs/import_1000.csv pour mesurer l'import de bout en bout (FP2).
Usage : python scripts/gen_import_csv.py        (1000 lignes)
        python scripts/gen_import_csv.py 200    (nombre au choix)
"""
import csv
import sys
from pathlib import Path

count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
path = Path("docs") / f"import_{count}.csv"
path.parent.mkdir(exist_ok=True)

with path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(
        ["email", "first_name", "last_name", "role", "matricule", "date_of_birth", "place_of_birth"]
    )
    for i in range(1, count + 1):
        writer.writerow([
            f"etu{i:04d}@univ-boumerdes.dz", f"Prenom{i}", f"Nom{i}",
            "student", f"2026{i:05d}", "2004-01-15", "Boumerdès",
        ])
print(f"{path} généré ({count} lignes)")
