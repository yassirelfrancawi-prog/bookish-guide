"""Validation de l'`initData` d'une Telegram WebApp (spec officielle).

Prouve que la requête vient bien de Telegram et identifie l'utilisateur, via un
HMAC-SHA256 calculé avec le token du bot. Indispensable avant toute génération.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def valider_init_data(init_data: str, bot_token: str, max_age_s: int = 86400) -> dict | None:
    """Retourne les champs validés (dont `user`) si l'initData est authentique, sinon None."""
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    recu = pairs.pop("hash", None)
    if not recu:
        return None

    # Chaîne de contrôle : paires key=value triées, jointes par \n.
    chaine = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    cle_secrete = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calcule = hmac.new(cle_secrete, chaine.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calcule, recu):
        return None

    # Anti-rejeu : initData périmé refusé.
    auth_date = int(pairs.get("auth_date", "0"))
    if max_age_s and (time.time() - auth_date) > max_age_s:
        return None

    if "user" in pairs:
        pairs["user"] = json.loads(pairs["user"])
    return pairs
