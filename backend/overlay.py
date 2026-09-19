"""Moteur d'overlay générique : superpose des valeurs sur un PDF original, au mm.

Principe : on garde le PDF d'origine comme fond (décor intact = fidélité au mm par
construction), on masque (redaction) les zones des champs variables, puis on tamponne
les nouvelles valeurs avec la police d'origine (cf. fonts.police_overlay).

Un seul moteur pour tous les templates ; chaque template = une carte de `Champ`.
"""
from dataclasses import dataclass

import fitz

from fonts import police_overlay

BLANC = (1, 1, 1)
NOIR = (0, 0, 0)
# Marge verticale retirée du rectangle de redaction : les boîtes de lignes voisines
# se chevauchent souvent de ~1-2 pt, et apply_redactions efface tout glyphe qui les
# touche. On rétrécit donc verticalement pour ne pas mordre sur la ligne du dessus/dessous.
MARGE_V = 2.0


@dataclass
class Champ:
    nom: str        # nom logique du champ (clé dans `valeurs`)
    rect: tuple     # (x0, y0, x1, y1) : zone à masquer puis tamponner
    police: str     # basefont d'origine (ex. 'Helvetica-Bold', 'CIDFont+F1')
    taille: float
    baseline: float  # y de la ligne de base d'origine
    align: str = "left"  # 'left' | 'right'
    texte_origine: str = ""  # texte localisé dans l'échantillon, utile aux polices Type3


def _ouvrir(modele):
    if isinstance(modele, (bytes, bytearray)):
        return fitz.open(stream=modele, filetype="pdf")
    return fitz.open(modele)


def appliquer(modele, champs, valeurs: dict, page_index: int = 0) -> bytes:
    """Masque les champs présents dans `valeurs` puis y tamponne les nouvelles valeurs."""
    doc = _ouvrir(modele)
    page = doc[page_index]
    actifs = [c for c in champs if c.nom in valeurs]

    for c in actifs:
        x0, y0, x1, y1 = c.rect
        marge = min(MARGE_V, (y1 - y0) / 4)  # garde une hauteur suffisante
        page.add_redact_annot(fitz.Rect(x0, y0 + marge, x1, y1 - marge), fill=BLANC)
    page.apply_redactions()

    # Passe 1 : couvrir les résidus visuels (champs voisins peuvent légèrement overlap).
    # On dessine TOUS les rects blancs AVANT d'insérer le texte → un draw_rect ultérieur
    # ne peut pas écraser le texte d'un champ précédent (bug ligne adresse écrasée par
    # le draw_rect de la ligne ville quand leurs rects se chevauchent verticalement).
    for c in actifs:
        x0, y0, x1, y1 = c.rect
        marge = min(MARGE_V, (y1 - y0) / 4)
        page.draw_rect(fitz.Rect(x0, y0 + marge, x1, y1 - marge), color=BLANC, fill=BLANC, overlay=True)

    # Passe 2 : insertion du texte, après que tous les rects blancs soient posés.
    for c in actifs:
        texte = str(valeurs[c.nom])
        if not texte:
            continue  # rien à écrire (zone juste effacée)
        fname = police_overlay(doc, page, c.police, texte)
        taille = _taille_effective(c, fname)
        x0, _, x1, _ = c.rect
        if c.align == "right":
            x0 = x1 - fitz.get_text_length(texte, fontname=fname, fontsize=taille)
        page.insert_text((x0, c.baseline), texte, fontname=fname, fontsize=taille, color=NOIR)

    return doc.tobytes()


def _taille_effective(c: Champ, fontname: str) -> float:
    """Recalibre les polices Type3 non réutilisables avec une police intégrée."""
    if c.police.lower().startswith("f") and c.police[1:].isdigit() and c.texte_origine:
        largeur = c.rect[2] - c.rect[0]
        ref = fitz.get_text_length(c.texte_origine, fontname=fontname, fontsize=1)
        if ref > 0:
            taille = largeur / ref
            if 4 <= taille <= c.taille:
                return taille
    return c.taille


def extraire(modele, champs, page_index: int = 0) -> dict:
    """Lit les valeurs d'une fiche aux positions de la carte de champs.

    Inverse de `appliquer` : la même carte sert de LECTEUR. Pour une fiche du
    même modèle (positions identiques, valeurs différentes), récupère ses valeurs.
    """
    doc = _ouvrir(modele)
    page = doc[page_index]
    out = {}
    for c in champs:
        x0, _, x1, _ = c.rect
        # bande verticale serrée autour de la ligne de base → évite les lignes voisines
        r = fitz.Rect(x0, c.baseline - c.taille, x1, c.baseline + c.taille * 0.3)
        out[c.nom] = page.get_textbox(r).strip().replace("\n", " ")
    return out


def _span_au_point(spans, x, y):
    """Span dont la bbox contient (x, y) — pour récupérer police/taille/baseline."""
    candidats = []
    for s in spans:
        b = s["bbox"]
        if b[0] - 1 <= x <= b[2] + 1 and b[1] - 1 <= y <= b[3] + 1:
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            candidats.append((abs(cy - y) + abs(cx - x) * 0.01, s))
    return min(candidats, key=lambda item: item[0])[1] if candidats else None


def carte_depuis_echantillon(pdf, reperes: dict, page_index: int = 0) -> list[Champ]:
    """Construit une carte de champs (semi-auto) en localisant des valeurs connues.

    `reperes` : {nom_logique: (texte, align[, mode[, choix]])}.
      - mode "span" (défaut) : la valeur est un span entier (montant, identité).
        align "right" → span le plus à droite (colonne des montants),
        "left" → premier span.
      - mode "sous" : la valeur est une SOUS-CHAÎNE noyée dans une description
        (ex. « (Base: 2.967,84) ») → localisée par recherche de texte ;
        align "left"/"right" choisit l'occurrence la plus à gauche/droite.
        choix optionnel "top"/"bottom" choisit l'occurrence verticale.
    """
    doc = _ouvrir(pdf)
    page = doc[page_index]
    spans = [s for b in page.get_text("dict")["blocks"] if b.get("type") == 0
             for l in b["lines"] for s in l["spans"]]
    champs = []
    for nom, rep in reperes.items():
        texte, align = rep[0], rep[1]
        mode = rep[2] if len(rep) > 2 else "span"

        if mode == "zone":
            r = fitz.Rect(*texte)
            s = _span_au_point(spans, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
            police = s["font"] if s else "Helvetica"
            taille = s["size"] if s else 8.0
            baseline = s["origin"][1] if s else r.y1
            champs.append(Champ(nom, tuple(r), police, taille, baseline, align, s["text"] if s else ""))
            continue

        if mode == "sous":
            rects = page.search_for(texte)
            if not rects:
                raise ValueError(f"sous-chaîne introuvable : {texte!r}")
            choix = rep[3] if len(rep) > 3 else None
            if choix == "bottom":
                r = max(rects, key=lambda r: r.y0)
            elif choix == "top":
                r = min(rects, key=lambda r: r.y0)
            else:
                r = max(rects, key=lambda r: r.x0) if align == "right" else min(rects, key=lambda r: r.x0)
            s = _span_au_point(spans, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
            police = s["font"] if s else "Helvetica"
            taille = s["size"] if s else 8.0
            baseline = s["origin"][1] if s else r.y1
            champs.append(Champ(nom, (r.x0, r.y0, r.x1, r.y1), police, taille, baseline, "left", texte))
            continue

        if mode == "apres":
            # `texte` = libellé ; la valeur est le span non vide le plus proche À DROITE
            # sur la même rangée → robuste pour « libellé : valeur » multi-colonnes et
            # pour les lignes résumé portant plusieurs valeurs.
            lab = next((x for x in spans if texte in x["text"]), None)
            rects = [] if lab is not None else page.search_for(texte)
            if lab is None and not rects:
                raise ValueError(f"libellé introuvable : {texte!r}")
            rb = lab["bbox"] if lab is not None else rects[0]
            y = (rb[1] + rb[3]) / 2
            droite = [x for x in spans if x["bbox"][0] >= rb[2] - 1
                      and x["bbox"][1] <= y <= x["bbox"][3] and x["text"].strip()]
            if not droite:
                raise ValueError(f"valeur après le libellé introuvable : {texte!r}")
            choix = rep[3] if len(rep) > 3 else None
            s = max(droite, key=lambda x: x["bbox"][2]) if choix == "last" else min(droite, key=lambda x: x["bbox"][0])
            champs.append(Champ(nom, tuple(s["bbox"]), s["font"], s["size"], s["origin"][1], align, s["text"]))
            continue

        if mode == "avant":
            # Miroir d'« apres » : la valeur est le span non vide le plus proche À GAUCHE
            # du libellé sur la même rangée. Utile quand la colonne montants est À GAUCHE
            # du libellé (ex. Securex : code | jours | heures | coeff | MONTANT | libellé).
            # `search_for` (vs `in text`) gère l'ancre multi-mot et trouve le libellé même
            # si ses mots sont fragmentés en spans séparés ; les décorations « ** » / « * »
            # voisines sont filtrées pour ne pas être prises pour la valeur.
            rects = page.search_for(texte)
            if not rects:
                raise ValueError(f"libellé introuvable : {texte!r}")
            r = rects[0]
            y = (r.y0 + r.y1) / 2
            gauche = [x for x in spans
                      if x["bbox"][2] <= r.x0 + 1
                      and x["bbox"][1] <= y <= x["bbox"][3]
                      and x["text"].strip()
                      and not all(c in "*•" for c in x["text"].replace(" ", ""))]
            if not gauche:
                raise ValueError(f"valeur avant le libellé introuvable : {texte!r}")
            s = max(gauche, key=lambda x: x["bbox"][2])
            champs.append(Champ(nom, tuple(s["bbox"]), s["font"], s["size"], s["origin"][1], align, s["text"]))
            continue

        if mode == "dessous":
            # `texte` = libellé ; la valeur est le span non vide juste EN DESSOUS,
            # avec recouvrement horizontal (ex. ligne résumé : libellés puis valeurs dessous).
            lab = next((x for x in spans if texte in x["text"]), None)
            if lab is None:
                raise ValueError(f"libellé introuvable : {texte!r}")
            lx0, _, lx1, ly1 = lab["bbox"]
            bas = [x for x in spans if x["bbox"][1] >= ly1 - 1 and x["text"].strip()
                   and x["bbox"][0] < lx1 and x["bbox"][2] > lx0]
            if not bas:
                raise ValueError(f"valeur sous le libellé introuvable : {texte!r}")
            s = min(bas, key=lambda x: x["bbox"][1])
            champs.append(Champ(nom, tuple(s["bbox"]), s["font"], s["size"], s["origin"][1], align, s["text"]))
            continue

        if mode == "ligne":
            # `texte` = libellé de la rangée ; la valeur est le span le plus à droite
            # de la même rangée. Robuste même si plusieurs valeurs sont égales (chaque
            # libellé est unique) → résout montants ET champs « libellé : valeur ».
            desc = next((x for x in spans if texte in x["text"]), None)
            if desc is None:
                raise ValueError(f"libellé de ligne introuvable : {texte!r}")
            y = (desc["bbox"][1] + desc["bbox"][3]) / 2
            rangee = [x for x in spans if x["bbox"][1] <= y <= x["bbox"][3]]
            s = max(rangee, key=lambda x: x["bbox"][2])
            champs.append(Champ(nom, tuple(s["bbox"]), s["font"], s["size"], s["origin"][1], align, s["text"]))
            continue

        matches = [x for x in spans if texte in x["text"]]
        if not matches:
            raise ValueError(f"repère introuvable dans l'échantillon : {texte!r}")
        # Désambiguïsation : un montant (aligné à droite) est dans la colonne des
        # montants → on prend le span le plus à droite, pas un libellé « (Base: …) ».
        s = max(matches, key=lambda x: x["bbox"][2]) if align == "right" else matches[0]
        champs.append(Champ(nom, tuple(s["bbox"]), s["font"], s["size"], s["origin"][1], align, s["text"]))
    return champs
