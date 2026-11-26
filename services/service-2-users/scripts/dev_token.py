"""
DEV UNIQUEMENT : génère une paire de clés RSA de test + un JWT, pour tester S2
sans attendre S1.  Usage (depuis la racine du service) :
    python scripts/dev_token.py admin
    python scripts/dev_token.py supervisor
En production, keys/auth_public.pem est la clé publique réelle de S1.
"""
import datetime as dt
import sys
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

keys_dir = Path("keys")
keys_dir.mkdir(exist_ok=True)
private_path = keys_dir / "dev_private.pem"
public_path = keys_dir / "auth_public.pem"

if not private_path.exists():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print("Clés de test générées dans keys/\n")

role = sys.argv[1] if len(sys.argv) > 1 else "admin"
now = dt.datetime.now(dt.timezone.utc)
payload = {
    "sub": sys.argv[2] if len(sys.argv) > 2 else str(uuid.uuid4()),
    "role": role,
    "iat": now,
    "exp": now + dt.timedelta(hours=8),
}
print(jwt.encode(payload, private_path.read_text(), algorithm="RS256"))