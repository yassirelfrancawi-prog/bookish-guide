"""Moteur de fiche GÉNÉRIQUE et configurable (HTML/CSS → PDF).

Gère n'importe quel profil (marié/isolé, enfants, ATN, voiture de société,
dirigeant…) : le corps est une liste de SECTIONS, chacune une liste de lignes
libres. Le moteur somme les lignes (cumul courant) pour les sous-totaux et le net
— l'arithmétique qu'on maîtrise. Les MONTANTS sont fournis (valeurs réelles du
client) : exact par construction, sans calcul réglementaire.
"""
from decimal import Decimal as D
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from formats import eur_be

TEMPLATES = Path(__file__).parent / "templates"


def preparer(fiche: dict) -> dict:
    """Calcule les sous-totaux (cumul courant) et le net à partir des lignes."""
    d = dict(fiche)
    cumul = D("0")
    sections = []
    for sec in fiche["sections"]:
        lignes = []
        for l in sec["lignes"]:
            montant = D(str(l["montant"]))
            cumul += montant
            lignes.append({**l, "montant_fmt": eur_be(montant)})
        sections.append({"label": sec["label"], "lignes": lignes, "total_fmt": eur_be(cumul)})
    d["sections"] = sections
    d["net_fmt"] = eur_be(cumul)
    d.setdefault("footer_marque", "")
    d.setdefault("pagination", "")
    return d


def rendre(fiche: dict, sortie: str | None = None) -> bytes:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    html = env.get_template("fiche_generique.html").render(**preparer(fiche))
    pdf = HTML(string=html).write_pdf()
    if sortie:
        with open(sortie, "wb") as f:
            f.write(pdf)
    return pdf
