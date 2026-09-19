"""Moteur de paie belge — employé (tranche verticale, option 1).

Périmètre actuel :
- On MAÎTRISE et on calcule : l'assemblage (brut → imposable → net) et l'ONSS
  théorique (13,07 %) à titre de contrôle.
- On PREND EN ENTRÉE (réglementaire, pas encore reconcilié) : le bonus à l'emploi
  social, le précompte professionnel et ses réductions, la CSSS.

Cible de validation : la fiche SD Worx réelle de mars 2026
(employé, célibataire, sans personne à charge) → salaire net = 2.508,94 €.
"""
from dataclasses import dataclass
from decimal import Decimal as D, ROUND_HALF_UP

from baremes_be import (
    ONSS_TAUX,
    BAREME_BASE, FRAIS_FORFAIT_TAUX, FRAIS_FORFAIT_MAX, FRAIS_FORFAIT_SEUIL,
    IMPOT_EXEMPTE_ISOLE, work_bonus_bareme,
)


def eur(x: D) -> D:
    """Arrondi monétaire au centime."""
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def bonus_emploi_volets(brut: D, ouvrier: bool = False, periode_debut: str = "") -> tuple[D, D]:
    """Volets A et B du bonus à l'emploi SOCIAL, séparément.

    On retourne A et B séparés pour pouvoir appliquer la réduction de précompte
    (33,14 % de A + 52,54 % de B, n° 46.2 de l'Annexe III).
    """
    bareme = work_bonus_bareme(periode_debut, ouvrier)

    def volet(p: dict) -> D:
        if brut <= p["S0"]:
            return p["R"]
        if brut <= p["S1"]:
            return eur(p["R"] - p["alpha"] * (brut - p["S0"]))
        return D("0")

    return eur(volet(bareme["A"])), eur(volet(bareme["B"]))


def bonus_emploi_base(brut: D, ouvrier: bool = False, periode_debut: str = "") -> D:
    """Bonus à l'emploi SOCIAL de base = volet A + volet B (S = brut mensuel)."""
    a, b = bonus_emploi_volets(brut, ouvrier, periode_debut)
    return eur(a + b)


def bareme_base(rni: D) -> D:
    """Impôt de base annuel via le barème de base (Annexe 1, formule-clé 2026)."""
    seuil_prec = D("0")
    for plafond, taux, cumul in BAREME_BASE:
        if plafond is None or rni <= plafond:
            return cumul + (rni - seuil_prec) * taux
        seuil_prec = plafond
    raise AssertionError("barème incomplet")


def precompte_mensuel_isole(base_mensuelle: D, impot_exempte: D = IMPOT_EXEMPTE_ISOLE) -> D:
    """Précompte professionnel mensuel — isolé sans charge (méthode officielle, 5 étapes).

    Source : formule-clé SPF Finances 1er janvier 2026. La valeur réformée de mars
    2026 (quotité exemptée relevée) n'étant pas publiée, `impot_exempte` est
    injectable pour reconcilier une fiche réelle post-réforme.
    """
    rab = base_mensuelle * 12  # A. revenu annuel brut (base déjà nette de cotis. sociales)
    frais = rab * FRAIS_FORFAIT_TAUX if rab <= FRAIS_FORFAIT_SEUIL else FRAIS_FORFAIT_MAX  # B.
    rni = rab - frais
    impot_base = max(bareme_base(rni) - impot_exempte, D("0"))  # C.
    return eur(impot_base / 12)  # D.


@dataclass
class Entrees:
    salaire_base: D            # rémunération brute de base
    supplements: D = D("0")    # suppléments soumis ONSS (heures supp, extra-légal…)

    # --- briques réglementaires FOURNIES (en attendant un calcul vérifié) -----
    onss: D = D("0")                  # cotisation ONSS (ligne brute, montant positif)
    bonus_emploi_social: D = D("0")   # réduction de l'ONSS (work bonus social)
    precompte: D = D("0")             # précompte sur rémunérations normales (positif)
    reductions_precompte: D = D("0")  # bonus fiscal + diminution surtravail (réduisent le PP)
    csss: D = D("0")                  # cotisation spéciale de sécurité sociale

    # --- avantages non imposables (s'ajoutent au net) ------------------------
    avantages_net: D = D("0")         # abonnement transport, indemnité vêtements…

    # --- retenues sur le net -------------------------------------------------
    cheques_repas_perso: D = D("0")
    acompte: D = D("0")


@dataclass
class Resultat:
    montant_brut: D
    onss_net: D            # ONSS après déduction du work bonus
    imposable: D
    precompte_net: D       # précompte après réductions
    salaire_net: D
    montant_net: D
    onss_theorique: D      # contrôle : 13,07 % du brut
    ecart_onss: D          # onss fourni − onss théorique


def calculer(e: Entrees) -> Resultat:
    montant_brut = eur(e.salaire_base + e.supplements)

    onss_net = eur(e.onss - e.bonus_emploi_social)
    imposable = eur(montant_brut - onss_net)

    precompte_net = eur(e.precompte - e.reductions_precompte)
    salaire_net = eur(
        imposable - precompte_net + e.avantages_net - e.csss - e.cheques_repas_perso
    )
    montant_net = eur(salaire_net - e.acompte)

    onss_theorique = eur(montant_brut * ONSS_TAUX)
    return Resultat(
        montant_brut=montant_brut,
        onss_net=onss_net,
        imposable=imposable,
        precompte_net=precompte_net,
        salaire_net=salaire_net,
        montant_net=montant_net,
        onss_theorique=onss_theorique,
        ecart_onss=eur(e.onss - onss_theorique),
    )


# --- Modèle de lignes du bulletin (source unique pour calcul ET affichage) ---
class Cat:
    """Catégorie d'une ligne : comment elle participe au calcul."""
    BRUT = "brut"               # composantes du brut (positif)
    ONSS = "onss"               # retenue ONSS (négatif à l'affichage)
    BONUS = "bonus"             # bonus à l'emploi, réduit l'ONSS (positif)
    PRECOMPTE = "precompte"     # précompte (négatif à l'affichage)
    RED_PRECOMPTE = "red_precompte"  # réductions du précompte (positif)
    AVANTAGE = "avantage"       # avantage non imposable, ajouté au net (positif)
    CSSS = "csss"               # cotisation spéciale (négatif à l'affichage)
    CHEQUE = "cheque"           # contribution chèques repas (négatif)
    ACOMPTE = "acompte"         # acompte déjà versé (négatif)


@dataclass
class Ligne:
    code: str
    desc: str
    montant: D    # signe tel qu'affiché sur la fiche
    cat: str


def agreger(lignes: list[Ligne]) -> Entrees:
    """Agrège des lignes signées en Entrees (montants normalisés positifs)."""
    somme = lambda c: sum((l.montant for l in lignes if l.cat == c), D("0"))
    return Entrees(
        salaire_base=somme(Cat.BRUT),
        onss=-somme(Cat.ONSS),
        bonus_emploi_social=somme(Cat.BONUS),
        precompte=-somme(Cat.PRECOMPTE),
        reductions_precompte=somme(Cat.RED_PRECOMPTE),
        csss=-somme(Cat.CSSS),
        avantages_net=somme(Cat.AVANTAGE),
        cheques_repas_perso=-somme(Cat.CHEQUE),
        acompte=-somme(Cat.ACOMPTE),
    )


# --- Validation contre l'oracle (fiche SD Worx, mars 2026) -------------------
if __name__ == "__main__":
    oracle = Entrees(
        salaire_base=D("2963.81"),
        supplements=D("1.07") + D("2.96"),          # 17C1 + 1723
        onss=D("387.90"),                            # ligne 2500
        bonus_emploi_social=D("56.66") + D("120.59"),# 2506 + 2509
        precompte=D("368.95"),                       # ligne 3500
        reductions_precompte=D("1.24") + D("39.96") + D("29.77"),  # 3700 + 3702 + 3704
        csss=D("14.48"),                             # ligne 3650
        avantages_net=D("65.83") + D("18.00"),       # 3010 + 3101
        cheques_repas_perso=D("19.62"),              # ligne 3970
        acompte=D("350.00"),                         # 3802 (montant déduit du net)
    )
    attendu = {
        "montant_brut": D("2967.84"),
        "imposable": D("2757.19"),
        "salaire_net": D("2508.94"),
        "montant_net": D("2158.94"),
    }

    r = calculer(oracle)
    lignes = [
        ("Montant brut", r.montant_brut, attendu["montant_brut"]),
        ("Imposable", r.imposable, attendu["imposable"]),
        ("Salaire net", r.salaire_net, attendu["salaire_net"]),
        ("Montant net", r.montant_net, attendu["montant_net"]),
    ]
    print(f"{'Poste':<16}{'Calculé':>12}{'Fiche':>12}{'':>4}")
    ok = True
    for nom, calc, att in lignes:
        match = calc == att
        ok = ok and match
        print(f"{nom:<16}{str(calc):>12}{str(att):>12}  {'OK' if match else 'ECART'}")
    print(f"\nContrôle ONSS théorique (13,07 %) : {r.onss_theorique}  "
          f"(fiche 387,90 → écart {r.ecart_onss})")

    base = bonus_emploi_base(r.montant_brut)
    print(f"Bonus à l'emploi de base calculé (volet A+B) : {base}")
    print(f"  fiche (base + renforcement 2026)           : 177.25")
    print(f"  → renforcement 2026 non sourçable          : {eur(D('177.25') - base)} (entrée)")

    pp_janv = precompte_mensuel_isole(r.imposable)
    print(f"\nPrécompte calculé (méthode officielle, exempt 1er janv. 2026) : {pp_janv}")
    print(f"  fiche (réforme De Wever mars 2026)                          : 368.95")
    print(f"  → réforme non publiée par le SPF : exempt à relever de "
          f"{IMPOT_EXEMPTE_ISOLE} vers ~4453 (quotité ~16650)")
    print("\nRÉSULTAT :", "reconcilié au centime ✓" if ok else "écarts détectés ✗")
