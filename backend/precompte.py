"""Précompte professionnel — moteur d'après l'Annexe III à l'AR du 11/12/2025
(`regle.pdf`), règles applicables au 1er janvier 2026.

Étapes (réf. Annexe III) :
  1. base mensuelle → (dirigeant : moins la réduction n°25.2) → × 12 = revenu annuel brut ;
  2. frais forfaitaires (n°28 travailleurs 30 %/6.070 ; n°29 dirigeants 3 %/3.200) → net imposable ;
  3. barème de base (n°31) ;
  4. impôt de base : isolé/conjoint-avec-revenus −2.987,98 (n°32) ou quotient conjugal (n°34) ;
  5. réductions enfants à charge (n°38) ;
  6. ÷ 12 = précompte mensuel.
Arrondi au cent à chaque étape.

NB : version « 1er janvier 2026 ». Une réforme en cours d'année 2026 modifie ces
valeurs (cf. fiches de mars) → à brancher dès qu'on a l'Annexe III réformée.
"""
from decimal import Decimal as D, ROUND_HALF_UP


def cent(x: D) -> D:
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


# Barème de base (n°31) : (plafond, taux, impôt cumulé jusqu'au seuil inférieur)
BAREME = [
    (D("16710"), D("0.2675"), D("0")),
    (D("29500"), D("0.4280"), D("4469.93")),
    (D("51050"), D("0.4815"), D("9944.05")),
    (None,       D("0.5350"), D("20320.38")),
]
EXEMPT_ISOLE = D("2987.98")   # impôt sur la quotité exemptée (11.170)
EXEMPT_MARIE = D("5975.96")   # 2× (conjoint sans revenus propres)
IMPUTE_MAX = D("13790")       # plafond du revenu imputé au conjoint

REDUC_ENFANTS = {0: D("0"), 1: D("624"), 2: D("1656"), 3: D("4404"), 4: D("7620"),
                 5: D("11100"), 6: D("14592"), 7: D("18120"), 8: D("21996")}


def _bareme(rni: D) -> D:
    seuil = D("0")
    for plafond, taux, cumul in BAREME:
        if plafond is None or rni <= plafond:
            return cent(cumul + (rni - seuil) * taux)
        seuil = plafond
    raise AssertionError


def _reduction_dirigeant(brut: D) -> D:
    """Réduction de base mensuelle des dirigeants (n°25.2)."""
    if brut <= D("1465"):
        return D("385")
    if brut <= D("6310"):
        return cent(D("385") + D("0.215") * (brut - D("1465")))
    if brut <= D("9290"):
        return cent(D("1426.68") + D("0.1450") * (brut - D("6310")))
    return D("1858.78")


def _reduction_enfants(n: int) -> D:
    if n <= 8:
        return REDUC_ENFANTS[n]
    return D("21996") + D("3864") * (n - 8)


def precompte_mensuel(base_mensuelle, dirigeant=False, conjoint_sans_revenus=False, enfants=0) -> D:
    """Précompte professionnel mensuel (€). `base_mensuelle` = imposable mensuel."""
    base = D(str(base_mensuelle))
    if dirigeant:
        base = cent(base - _reduction_dirigeant(base))
    rab = cent(base * 12)

    taux, plafond = (D("0.03"), D("3200")) if dirigeant else (D("0.30"), D("6070"))
    rni = cent(rab - cent(min(rab * taux, plafond)))

    if conjoint_sans_revenus:
        impute = min(cent(rni * D("0.30")), IMPUTE_MAX)
        impot = cent(_bareme(impute) + _bareme(rni - impute) - EXEMPT_MARIE)
    else:
        impot = cent(_bareme(rni) - EXEMPT_ISOLE)

    impot = max(impot - _reduction_enfants(enfants), D("0"))
    return cent(impot / 12)


if __name__ == "__main__":
    # 1) Cas isolé employé 3.000 € → la formule-clé officielle donne 596,93
    print("Isolé employé 3.000 € :", precompte_mensuel("3000"), "(attendu 596,93)")
    # 2) Cas dirigeant B B PHARMA (marié conjoint avec revenus, base 3.407,96)
    print("Dirigeant B B PHARMA  :", precompte_mensuel("3407.96", dirigeant=True), "(fiche 608,93)")
    # 3) Cas isolé employé 2.757,19 (07e, règles de janvier)
    print("Isolé employé 2.757,19:", precompte_mensuel("2757.19"), "(07e mars→369, janvier→491)")
