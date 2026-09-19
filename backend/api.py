"""API FastAPI : reçoit les données de la fiche, calcule, rend le PDF, et —
si un bot est configuré — le poste dans le chat Telegram.

Lancement local :  .venv/bin/uvicorn api:app --reload  (depuis backend/)
Configuration :    backend/.env  (voir .env.example) — BOT_TOKEN + ALLOWED_IDS.
"""
import io
import os
import zipfile
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

# Charge backend/.env si présent (BOT_TOKEN, ALLOWED_IDS).
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from moteur_be import Cat, Ligne, agreger, calculer
from rendu_pdf import donnees, rendre_bytes
from telegram_auth import valider_init_data
from bot import envoyer_pdf
from overlay import appliquer
from rendu_generique import rendre as rendre_generique
from composer import composer_be
import registre

CATS_VALIDES = {v for k, v in vars(Cat).items() if not k.startswith("_")}

app = FastAPI(title="Certifio — génération de fiches de paie")


class LigneIn(BaseModel):
    code: str = ""
    desc: str
    montant: Decimal
    cat: str

    @field_validator("cat")
    @classmethod
    def cat_connue(cls, v: str) -> str:
        if v not in CATS_VALIDES:
            raise ValueError(f"catégorie inconnue : {v} (attendu : {sorted(CATS_VALIDES)})")
        return v


class FicheIn(BaseModel):
    lignes: list[LigneIn]
    identite: dict | None = None
    init_data: str | None = None  # initData Telegram (validé si un bot est configuré)


@app.get("/api/sante")
def sante() -> dict:
    return {"ok": True, "bot_configure": bool(os.environ.get("BOT_TOKEN"))}


def _ids_autorises() -> set[int]:
    raw = os.environ.get("ALLOWED_IDS", "").strip()
    return {int(x) for x in raw.split(",") if x.strip().isdigit()} if raw else set()


def _chat_id_si_bot(init_data: str | None):
    """Si un bot est configuré, valide l'initData + ACL et renvoie le chat_id ; sinon None.

    - Pas de BOT_TOKEN : mode local sans auth, retourne None.
    - BOT_TOKEN défini + ALLOWED_IDS vide : tout user Telegram valide est accepté.
    - BOT_TOKEN défini + ALLOWED_IDS non vide : seuls ces user_id passent (403 sinon).
    """
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return None
    if not init_data:
        raise HTTPException(400, "init_data requis quand un bot est configuré")
    infos = valider_init_data(init_data, token)
    if infos is None:
        raise HTTPException(401, "initData Telegram invalide")
    user_id = infos["user"]["id"]
    autorises = _ids_autorises()
    if autorises and user_id not in autorises:
        raise HTTPException(403, "Accès refusé.")
    return user_id


def _reponse_pdf(pdf: bytes, chat_id, nom="fiche-de-paie.pdf", legende="Votre fiche de paie"):
    """Poste le PDF via le bot si un chat est identifié, sinon le renvoie en download."""
    token = os.environ.get("BOT_TOKEN")
    if token and chat_id:
        envoyer_pdf(chat_id, pdf, token, nom, legende)
        return {"ok": True, "envoye_chat": chat_id}
    return Response(
        pdf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nom}"},
    )


@app.post("/api/generer")
def generer(fiche: FicheIn):
    """Rendu HTML/CSS (plan B) : reconstruit la fiche depuis les lignes."""
    chat_id = _chat_id_si_bot(fiche.init_data)
    lignes = [Ligne(l.code, l.desc, l.montant, l.cat) for l in fiche.lignes]
    pdf = rendre_bytes(donnees(lignes, fiche.identite))
    return _reponse_pdf(pdf, chat_id)


@app.get("/api/templates/{cle}/preview")
def template_preview(cle: str):
    """Aperçu PNG du PDF original du template (page utile, basse résolution)."""
    import fitz
    t = registre.get(cle)
    if t is None:
        raise HTTPException(404, f"template inconnu : {cle}")
    doc = fitz.open(str(t.pdf))
    pix = doc[t.page_index].get_pixmap(dpi=90)
    return Response(pix.tobytes("png"), media_type="image/png")


@app.get("/api/templates")
def templates() -> dict:
    """Liste les templates overlay disponibles et leurs champs."""
    return {
        cle: {
            "nom": t.nom,
            "champs": list(t.reperes),
            "supporte_composer": t.mapper_config is not None,
            "supporte_atn": t.supporte_atn,
            "supporte_cheques_repas": t.supporte_cheques_repas,
            "supporte_fpe": t.supporte_fpe,
            "employeur_fixe": t.employeur_fixe,
        }
        for cle, t in registre.TEMPLATES.items()
    }


class OverlayIn(BaseModel):
    template: str
    valeurs: dict[str, str]
    init_data: str | None = None


@app.post("/api/generer-overlay")
def generer_overlay(req: OverlayIn):
    """Rendu overlay (au millimètre) : tamponne des valeurs fournies sur le PDF original."""
    t = registre.get(req.template)
    if t is None:
        raise HTTPException(404, f"template inconnu : {req.template}")
    chat_id = _chat_id_si_bot(req.init_data)
    pdf = appliquer(str(t.pdf), t.champs(), req.valeurs, t.page_index)
    return _reponse_pdf(pdf, chat_id)


class FicheGeneriqueIn(BaseModel):
    employeur: dict
    periode: dict
    perso: dict
    salarie: dict
    sections: list[dict]
    footer_marque: str = ""
    pagination: str = ""
    init_data: str | None = None


@app.post("/api/fiche-generique")
def fiche_generique(req: FicheGeneriqueIn):
    """Rendu HTML flexible : fiche configurable (sections fournies) → PDF."""
    chat_id = _chat_id_si_bot(req.init_data)
    fiche = req.model_dump(exclude={"init_data"})
    pdf = rendre_generique(fiche)
    return _reponse_pdf(pdf, chat_id)


class ConfigIn(BaseModel):
    employeur: dict
    periode: dict
    perso: dict
    salarie: dict
    situation: dict           # dirigeant, ouvrier, conjoint_sans_revenus, enfants
    brut: str
    cotisations: str = ""     # ONSS (vide = calculé auto)
    bonus_emploi: str = ""    # bonus à l'emploi (vide = calculé auto)
    atn: list[dict] = []
    voiture_modele: str = ""  # modèle ou marque (BB Pharma : remplace « Porsche » par défaut)
    cheques_repas: str = ""
    fpe: str = ""
    init_data: str | None = None


@app.post("/api/fiche-config")
def fiche_config(req: ConfigIn):
    """Entrées simples → précompte CALCULÉ → fiche assemblée → PDF."""
    chat_id = _chat_id_si_bot(req.init_data)
    cfg = req.model_dump(exclude={"init_data"})
    try:
        fiche = composer_be(cfg)
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(400, f"Saisie invalide : {e}")
    pdf = rendre_generique(fiche)
    return _reponse_pdf(pdf, chat_id)


class FicheOverlayConfigIn(ConfigIn):
    template: str


def _strip_pages(pdf_bytes: bytes, pages_a_garder: list | None) -> bytes:
    """Conserve uniquement les pages indiquées et purge les ressources orphelines."""
    if not pages_a_garder:
        return pdf_bytes
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc.select(pages_a_garder)
    # garbage=4 + deflate : nettoie fonts/images non référencées → PDF beaucoup plus léger.
    return doc.tobytes(garbage=4, deflate=True)


@app.post("/api/fiche-overlay")
def fiche_overlay(req: FicheOverlayConfigIn):
    """Entrées simples → composer → mapper du template → PDF au visuel du template."""
    t = registre.get(req.template)
    if t is None:
        raise HTTPException(404, f"template inconnu : {req.template}")
    if t.mapper_config is None:
        raise HTTPException(400, f"template sans mapper composer : {req.template}")
    chat_id = _chat_id_si_bot(req.init_data)
    cfg = req.model_dump(exclude={"init_data", "template"})
    try:
        fiche = composer_be(cfg)
        valeurs = t.mapper_config(fiche, cfg)
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(400, f"Saisie invalide : {e}")
    pdf = appliquer(str(t.pdf), t.champs(), valeurs, t.page_index)
    pdf = _strip_pages(pdf, t.pages_a_garder)
    return _reponse_pdf(pdf, chat_id)


def _periode_mois(annee: int, mois: int) -> dict:
    """Construit le dict periode (debut/fin/calcul) du mois donné, format JJ/MM/AAAA."""
    import calendar
    dernier = calendar.monthrange(annee, mois)[1]
    return {
        "debut": f"01/{mois:02d}/{annee}",
        "fin": f"{dernier:02d}/{mois:02d}/{annee}",
        "calcul": f"{dernier:02d}/{mois:02d}/{annee}",
    }


def _trois_mois_finissant(annee: int, mois: int):
    """Liste des 3 (annee, mois) finissant au mois donné, plus ancien au plus récent."""
    out = []
    for delta in range(2, -1, -1):
        m, a = mois - delta, annee
        while m < 1:
            m += 12
            a -= 1
        out.append((a, m))
    return out


class FicheOverlay3MoisIn(ConfigIn):
    template: str
    annee: int
    mois: int
    bruts: list[str] | None = None  # 3 bruts [m-2, m-1, m] ; si absent : brut répété 3×


@app.post("/api/fiche-overlay-3mois")
def fiche_overlay_3mois(req: FicheOverlay3MoisIn):
    """3 fiches d'affilée (mois courant + 2 précédents) → ZIP ou envoi Telegram.

    `bruts` optionnel : 3 valeurs [m-2, m-1, m] pour des salaires différents par mois.
    Si absent (ou liste partielle), on complète avec `brut` répété.
    """
    t = registre.get(req.template)
    if t is None:
        raise HTTPException(404, f"template inconnu : {req.template}")
    if t.mapper_config is None:
        raise HTTPException(400, f"template sans mapper composer : {req.template}")
    chat_id = _chat_id_si_bot(req.init_data)
    cfg_base = req.model_dump(exclude={"init_data", "template", "annee", "mois", "bruts"})

    # Brut par mois : utilise `bruts` si fourni, sinon `brut` répété.
    bruts_demandes = req.bruts or []
    bruts_par_mois = [
        (bruts_demandes[i].strip() if i < len(bruts_demandes) and bruts_demandes[i].strip() else req.brut)
        for i in range(3)
    ]

    pdfs = []
    try:
        for (a, m), brut in zip(_trois_mois_finissant(req.annee, req.mois), bruts_par_mois):
            cfg = {**cfg_base, "periode": _periode_mois(a, m), "brut": brut}
            fiche = composer_be(cfg)
            valeurs = t.mapper_config(fiche, cfg)
            pdf = appliquer(str(t.pdf), t.champs(), valeurs, t.page_index)
            pdf = _strip_pages(pdf, t.pages_a_garder)
            pdfs.append((f"fiche-{a}-{m:02d}.pdf", pdf))
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(400, f"Saisie invalide : {e}")

    token = os.environ.get("BOT_TOKEN")
    if token and chat_id:
        for nom, pdf in pdfs:
            envoyer_pdf(chat_id, pdf, token, nom, f"Fiche de paie {nom[6:13]}")
        return {"ok": True, "envoye_chat": chat_id, "nb": len(pdfs)}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nom, pdf in pdfs:
            z.writestr(nom, pdf)
    return Response(
        buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=fiches-3-mois.zip"},
    )


class TroisMoisIn(BaseModel):
    template: str
    valeurs: dict[str, str]
    annee: int
    mois: int
    init_data: str | None = None


def _mois_precedents(annee: int, mois: int, n: int = 3):
    """Les n mois se terminant à (annee, mois), du plus ancien au plus récent."""
    out = []
    for delta in range(n - 1, -1, -1):
        m, a = mois - delta, annee
        while m < 1:
            m += 12
            a -= 1
        out.append((a, m))
    return out


@app.post("/api/fiche-3mois")
def fiche_3mois(req: TroisMoisIn):
    """3 PDF pour les 3 mois finissant au mois choisi (ex. mai → mars, avril, mai)."""
    t = registre.get(req.template)
    if t is None:
        raise HTTPException(404, f"template inconnu : {req.template}")
    if t.periode is None:
        raise HTTPException(400, f"template sans gestion de période : {req.template}")
    chat_id = _chat_id_si_bot(req.init_data)
    token = os.environ.get("BOT_TOKEN")

    pdfs = []
    for a, m in _mois_precedents(req.annee, req.mois, 3):
        valeurs = {**req.valeurs, **t.periode(a, m)}
        pdfs.append((f"fiche-{a}-{m:02d}.pdf", appliquer(str(t.pdf), t.champs(), valeurs, t.page_index)))

    if token and chat_id:
        for nom, pdf in pdfs:
            envoyer_pdf(chat_id, pdf, token, nom, "Votre fiche de paie")
        return {"ok": True, "envoye_chat": chat_id, "nb": len(pdfs)}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nom, pdf in pdfs:
            z.writestr(nom, pdf)
    return Response(
        buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=fiches-3-mois.zip"},
    )


class FicheIn2(BaseModel):
    template: str
    lignes: list[LigneIn]
    identite: dict[str, str] | None = None
    init_data: str | None = None


@app.post("/api/fiche")
def fiche(req: FicheIn2):
    """Pipeline complet : lignes → moteur → mapper du template → overlay au mm."""
    t = registre.get(req.template)
    if t is None:
        raise HTTPException(404, f"template inconnu : {req.template}")
    if t.mapper is None:
        raise HTTPException(400, f"template sans mapper : {req.template}")
    chat_id = _chat_id_si_bot(req.init_data)
    lignes = [Ligne(l.code, l.desc, l.montant, l.cat) for l in req.lignes]
    resultat = calculer(agreger(lignes))
    valeurs = t.mapper(resultat, req.identite or {}, lignes)
    pdf = appliquer(str(t.pdf), t.champs(), valeurs, t.page_index)
    return _reponse_pdf(pdf, chat_id)
