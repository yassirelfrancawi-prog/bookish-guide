"""Composition d'une fiche BE à partir d'entrées simples.

Calcule automatiquement :
- ONSS personnelle : 13,07 % du brut (employé) ou de brut × 108 % (ouvrier — provision
  des pécules de vacances). Dirigeant : pas d'ONSS travailleur.
- Bonus à l'emploi social : formule officielle ONSS, employés et ouvriers, avec
  barème choisi selon la période (mars 2026 puis avril 2026).
- Réduction de précompte liée au bonus : 33,14 % du volet A + 52,54 % du volet B
  (Annexe III à l'AR du 11/12/2025, n° 46.2).
- Précompte professionnel : Annexe III complète (precompte.py).

Le client peut surcharger l'ONSS et le bonus en passant les champs `cotisations` et
`bonus_emploi` (chaînes vides = utilise le calcul auto).
"""
from decimal import Decimal as D

from baremes_be import ONSS_TAUX, WORK_BONUS_FISCAL_PCT
from moteur_be import bonus_emploi_volets, eur
from precompte import precompte_mensuel


def _d(x) -> D:
    """Decimal tolérant : accepte virgule décimale belge, espaces et signes vides."""
    s = str(x).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s or s in ("+", "-", "."):
        return D("0")
    return D(s)


def _onss_perso(brut_total: D, ouvrier: bool, dirigeant: bool) -> D:
    """ONSS travailleur, avec spécificité ouvrier (base × 108 %)."""
    if dirigeant:
        return D("0")
    base = brut_total * (D("1.08") if ouvrier else D("1.00"))
    return eur(base * ONSS_TAUX)


def _ecreter_bonus(a: D, b: D, plafond: D) -> tuple[D, D]:
    """Plafonne le bonus aux cotisations dues : écrêtement sur B puis sur A."""
    if a + b <= plafond:
        return a, b
    depassement = a + b - plafond
    reduction_b = min(b, depassement)
    b -= reduction_b
    depassement -= reduction_b
    a = max(a - depassement, D("0"))
    return eur(a), eur(b)


def _bonus_et_reduction(brut_total: D, ouvrier: bool, dirigeant: bool,
                        bonus_override: D | None, onss_perso: D,
                        periode_debut: str) -> tuple[D, D]:
    """Bonus à l'emploi social + réduction de précompte fiscale correspondante.

    Le bonus social ne peut jamais dépasser l'ONSS personnelle due.
    """
    if dirigeant:
        return D("0"), D("0")
    if bonus_override is not None:
        bonus = min(eur(bonus_override), onss_perso)
        return bonus, D("0")

    a, b = bonus_emploi_volets(brut_total, ouvrier, periode_debut)
    a, b = _ecreter_bonus(a, b, onss_perso)
    bonus = eur(a + b)
    reduction = eur(a * WORK_BONUS_FISCAL_PCT["A"] + b * WORK_BONUS_FISCAL_PCT["B"])
    return bonus, reduction


def composer_be(cfg: dict) -> dict:
    sit = cfg["situation"]
    atn = cfg.get("atn", [])
    ouvrier = bool(sit.get("ouvrier"))
    dirigeant = bool(sit.get("dirigeant"))

    # Brut + ATN : on borne au-dessus de 0 pour rester cohérent.
    brut = max(_d(cfg["brut"]), D("0"))
    if brut == 0 and not str(cfg["brut"]).strip():
        raise ValueError("brut requis")
    atn_total = sum((max(_d(a["montant"]), D("0")) for a in atn), D("0"))
    brut_total = brut + atn_total  # base soumise ONSS et imposable

    # ONSS : auto (avec surcharge possible)
    onss_override = str(cfg.get("cotisations", "")).strip()
    onss_perso = max(_d(onss_override), D("0")) if onss_override else _onss_perso(brut_total, ouvrier, dirigeant)

    # Bonus à l'emploi : auto (override possible)
    bonus_override = str(cfg.get("bonus_emploi", "")).strip()
    bonus_in = max(_d(bonus_override), D("0")) if bonus_override else None
    bonus_social, reduction_precompte = _bonus_et_reduction(
        brut_total, ouvrier, dirigeant, bonus_in, onss_perso,
        cfg["periode"].get("debut", "")
    )

    # Imposable = brut + ATN − ONSS + bonus social (borné ≥ 0)
    imposable = max(eur(brut_total - onss_perso + bonus_social), D("0"))

    # Précompte calculé sur l'imposable (enfants clampé à ≥ 0)
    enfants_brut = int(sit.get("enfants", 0) or 0)
    enfants = max(enfants_brut, 0)
    precompte_brut = precompte_mensuel(
        imposable, dirigeant=dirigeant,
        conjoint_sans_revenus=bool(sit.get("conjoint_sans_revenus")),
        enfants=enfants,
    )
    reduction_precompte = min(reduction_precompte, precompte_brut)
    precompte_net = precompte_brut - reduction_precompte

    # Section Imposable (ce qui s'affiche)
    imp = [("1011", "Rémunération brute", brut)]
    imp += [(a["code"], a["desc"], _d(a["montant"])) for a in atn]
    if onss_perso > 0:
        libelle_onss = f"ONSS personnelle ({'108 %' if ouvrier else '13,07 %'})"
        imp.append(("2500", libelle_onss, -onss_perso))
    if bonus_social > 0:
        imp.append(("2509", "Bonus à l'emploi", bonus_social))

    # Section Net
    net = [("3500", "Précompte professionnel", -precompte_brut)]
    if reduction_precompte > 0:
        net.append(("3702", "Réduction PP — bonus à l'emploi (fiscal)", reduction_precompte))
    net += [(a["code"], a["desc"], -_d(a["montant"])) for a in atn]  # ATN repris du net
    if str(cfg.get("cheques_repas", "")).strip():
        net.append(("3970", "Chèques-repas (CR)", -_d(cfg["cheques_repas"])))
    if str(cfg.get("fpe", "")).strip():
        net.append(("3330", "Frais mensuels généraux (FPE)", _d(cfg["fpe"])))

    net_a_payer = eur(sum((m for _, _, m in imp + net), D("0")))

    def lignes(rows):
        return [{"code": c, "desc": d, "montant": str(m)} for c, d, m in rows]

    statut_libelle = (
        "Dirigeant d'entreprise" if dirigeant
        else "Ouvrier(ère)" if ouvrier
        else "Employé(e)"
    )
    return {
        "employeur": cfg["employeur"],
        "periode": cfg["periode"],
        "perso": {
            **cfg["perso"],
            "charges": f"{int(sit.get('enfants', 0) or 0)} enfant(s)",
            "statut": statut_libelle,
        },
        "salarie": cfg["salarie"],
        "sections": [
            {"label": "Imposable", "lignes": lignes(imp)},
            {"label": "Net", "lignes": lignes(net)},
        ],
        "calculs": {
            "brut_total": str(brut_total),
            "onss_perso": str(onss_perso),
            "bonus_social": str(bonus_social),
            "imposable": str(imposable),
            "precompte_brut": str(precompte_brut),
            "reduction_precompte": str(reduction_precompte),
            "precompte_net": str(precompte_net),
            "net_a_payer": str(net_a_payer),
        },
    }
