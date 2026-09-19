"""Envoi du PDF dans le chat Telegram via l'API Bot (sendDocument)."""
import httpx

API = "https://api.telegram.org/bot{token}/sendDocument"


def envoyer_pdf(chat_id: int | str, pdf: bytes, bot_token: str,
                nom_fichier: str = "fiche.pdf", legende: str = "") -> dict:
    """Poste un PDF dans le chat. Lève une exception si l'API Telegram refuse."""
    r = httpx.post(
        API.format(token=bot_token),
        data={"chat_id": str(chat_id), "caption": legende},
        files={"document": (nom_fichier, pdf, "application/pdf")},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
