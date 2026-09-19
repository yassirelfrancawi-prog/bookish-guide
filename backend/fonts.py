"""Résolution de police pour l'overlay.

Pour chaque valeur à tamponner, on veut le MÊME typeface que l'original :
  1. police EMBARQUÉE du PDF SI elle couvre tous les glyphes du texte (exact) ;
  2. sinon une police COMPLÈTE équivalente (bundle fonts/, sinon police système) —
     gère le cas « glyphe absent du sous-ensemble » (ex. un « J » dans un nom) ;
  3. sinon une police INTÉGRÉE PyMuPDF (couverture latine complète).
"""
from pathlib import Path

import fitz

DOSSIER = Path(__file__).parent / "fonts"

INTEGREE = {
    "helvetica": "helv", "helvetica-bold": "hebo", "helvetica-oblique": "heit",
    "arial": "helv", "times": "tiro", "times-bold": "tibo",
    "courier": "cour", "courier-bold": "cobo",
}

# Polices libres équivalentes (Arimo↔Arial, Tinos↔Times), à déposer dans fonts/.
BUNDLE = {"arial": "Arimo-Regular.ttf", "times": "Tinos-Regular.ttf"}

# Repli DEV local (macOS) si aucune police bundlée — en prod, bundler dans fonts/.
SYSTEME = {
    "arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "times": "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
}


def _famille(nom: str) -> str:
    bas = nom.lower()
    if bas.startswith("f") and bas[1:].isdigit():
        return "courier"
    for cle in ("arial", "helvetica", "times", "courier"):
        if cle in bas:
            return cle
    return bas


def _slug(nom: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in nom)


def _fichier_complet(famille: str) -> str | None:
    """Police complète pour la famille : bundle fonts/ d'abord, sinon système."""
    b = DOSSIER / BUNDLE.get(famille, "")
    if b.is_file():
        return str(b)
    s = SYSTEME.get(famille)
    return s if s and Path(s).is_file() else None


def police_overlay(doc, page, police_origine: str, texte: str = "") -> str:
    """fontname PyMuPDF reproduisant `police_origine` et couvrant `texte`."""
    chars = [c for c in texte if c.strip()]

    # 1. police embarquée si elle couvre tous les glyphes du texte
    for f in doc.get_page_fonts(page.number):
        if f[3] == police_origine:
            buf = doc.extract_font(f[0])[3]
            if buf and all(fitz.Font(fontbuffer=buf).has_glyph(ord(c)) for c in chars):
                nom = "emb_" + _slug(police_origine)
                page.insert_font(fontname=nom, fontbuffer=buf)
                return nom
            break

    # 2. police complète équivalente (couvre tous les glyphes)
    complet = _fichier_complet(_famille(police_origine))
    if complet:
        nom = "full_" + _slug(_famille(police_origine))
        page.insert_font(fontname=nom, fontfile=complet)
        return nom

    # 3. police intégrée
    return INTEGREE.get(police_origine.lower(), INTEGREE.get(_famille(police_origine), "helv"))
